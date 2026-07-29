"""Put a card that already lives in asmDB onto the chain.

This module is the bridge that was missing. W9 built the chain layer (:mod:`app.chain`)
and W5 built the jobs, but no job ever imported the former, so every card was minted
into asmDB and left unanchored — the site rendered "ANCHOR PENDING" forever.

The job is deliberately *separate* from card creation. Anchoring is the step most
likely to fail for reasons that have nothing to do with the card: an RPC hiccup, an
empty gas tank, a congested testnet. A card that exists in asmDB is already the real
artefact, so a chain failure must never roll it back or block the day's bloom. Running
the anchor as its own step means a failure is retryable simply by running it again —
which is safe, because :meth:`app.chain.Anchorer.anchor` is idempotent on the serial
and this job skips a serial that already carries its anchor row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.asmdb import AsmDbNotFound
from app.asmdb import Row as AsmDbRow
from app.chain import AnchorReceipt, AnchorResult, build_anchor_row_from_result
from app.chain.config import ChainSettings, load_chain_settings
from app.codec import Card, card_hash, decode
from app.core.logging import card_context, get_logger

from ._operations import to_asmdb_rows, to_codec_rows
from .models import JobRepository

_log = get_logger(__name__)

#: Row id of the anchor part, mirroring ``serial * 16 + ANCHOR_PART`` (docs/CODEC.md §4.3).
_ANCHOR_PART = 8

#: Where a marketplace should look for a card's ERC-721 metadata.
#:
#: This must address ``/api/nft/``, not ``/api/cards/``: the latter returns the site's
#: own card payload, which is not ERC-721 metadata and which a marketplace cannot read.
#: The host is ``www`` because that is the name with a certificate. PS-0001 was minted
#: pointing at ``https://pixelslime.cloud/api/cards/1`` — wrong on both counts — and a
#: tokenURI cannot be rewritten after the mint, so that one card is permanently
#: mis-addressed. Everything after it is not.
DEFAULT_TOKEN_URI_BASE = "https://www.pixelslime.cloud/api/nft/"


class CardAnchorer(Protocol):
    """The chain surface this job needs — satisfied by :class:`app.chain.Anchorer`."""

    def anchor(self, serial: int, card_hash: bytes, token_uri: str) -> AnchorReceipt: ...

    def find_mint(self, serial: int) -> AnchorResult | None:
        """Recover the original mint of ``serial`` from chain history, if any."""
        ...


class AnchorRowStore(Protocol):
    """Reads and writes the single addressed anchor row — satisfied by :class:`AsmDbClient`.

    The anchor row is deliberately *not* handled through the repository's card
    methods. :meth:`JobRepository.write_card_rows` validates its input as the
    complete contiguous set of parts for one card starting at zero, and
    :meth:`JobRepository.read_card_rows` returns only those same card parts — the
    part 8 anchor is invisible to it. Addressing the row directly keeps the
    whole-card invariant intact and lets a re-run detect its own previous success.
    """

    async def get(self, row_id: int) -> AsmDbRow: ...

    async def upsert(self, row: AsmDbRow) -> AsmDbRow: ...


class BloomRecorder(Protocol):
    """Records the economic half of a bloom — satisfied by :class:`ClaimPoolWriter`.

    Kept separate from :class:`CardAnchorer` because the two do genuinely different
    things: anchoring mints the SLIME card (ERC-721) and is *not* repeatable, while
    recording the bloom moves SMILE (ERC-20) — burning the fee out of the finite
    Genesis Rain and minting the yield into the Claim Pool.
    """

    def record_bloom(self, serial: int, rarity: str, happiness: int) -> bytes | None: ...


@dataclass(frozen=True, slots=True)
class AnchorDependencies:
    """Injected boundaries so the job runs against a stub with no chain present."""

    repository: JobRepository
    writer: AnchorRowStore
    anchorer: CardAnchorer
    bloom: BloomRecorder | None = None
    token_uri_base: str = DEFAULT_TOKEN_URI_BASE


@dataclass(frozen=True, slots=True)
class AnchorOutcome:
    """What one anchor attempt did.

    ``anchored`` is False for a serial the chain already knows about, which is a
    success, not a failure — it is what a re-run of a partially completed day looks
    like.
    """

    serial: int
    anchored: bool
    tx_hash: bytes | None = None
    block_number: int | None = None


def _card_from_rows(rows: list[AsmDbRow]) -> Card:
    """Decode the asmDB rows of one serial back into its canonical card."""
    return decode(to_codec_rows(rows))


async def anchor_serial(serial: int, *, deps: AnchorDependencies) -> AnchorOutcome:
    """Anchor one serial, writing its anchor row back to asmDB on success.

    Raises :class:`LookupError` when the serial has no rows: anchoring a card that
    does not exist would mint a hash of nothing, so it fails loudly rather than
    writing a meaningless commitment to a public chain.
    """
    with card_context(serial):
        anchor_row_id = serial * 16 + _ANCHOR_PART

        # Ask for the anchor row by its deterministic id. read_card_rows cannot answer
        # this: it returns the card's own contiguous parts and never part 8, so relying
        # on it made every run re-scan chain logs for work already done.
        try:
            await deps.writer.get(anchor_row_id)
        except AsmDbNotFound:
            pass
        else:
            # The card is already anchored, so the mint must not be retried — it is not
            # repeatable. The bloom is a different matter: it is a separate, retryable
            # act, and a previous run may have anchored successfully and then failed to
            # record it. Returning here without re-attempting would strand that card
            # unbloomed forever, leaving the ten-year schedule quietly short. Repeating
            # a bloom that did succeed is safe — the pool refuses it.
            _log.info("anchor_row_already_present", serial=serial)
            rows = await deps.repository.read_card_rows(serial)
            if rows:
                _record_bloom(deps, _card_from_rows(rows))
            return AnchorOutcome(serial=serial, anchored=False)

        rows = await deps.repository.read_card_rows(serial)
        if not rows:
            raise LookupError(f"serial {serial} has no rows in asmDB; nothing to anchor")

        card = _card_from_rows([r for r in rows if r.id != anchor_row_id])
        digest = card_hash(card)
        token_uri = f"{deps.token_uri_base}{serial}"

        receipt = deps.anchorer.anchor(serial, digest, token_uri)
        if receipt.already_minted:
            # The chain has the card but asmDB does not have the row, so the process
            # died in the window between the two writes. The mint is not repeatable,
            # so the only way to heal is to go and find the transaction that already
            # happened. Without this the card would show ANCHOR PENDING forever
            # despite being provably on-chain.
            recovered = deps.anchorer.find_mint(serial)
            if recovered is None:
                _log.warning("anchor_mint_unrecoverable", serial=serial)
                return AnchorOutcome(serial=serial, anchored=False)
            _log.info("anchor_recovered_existing_mint", serial=serial)
            await deps.writer.upsert(to_asmdb_rows([build_anchor_row_from_result(recovered)])[0])
            _record_bloom(deps, card)
            return AnchorOutcome(
                serial=serial,
                anchored=True,
                tx_hash=recovered.tx_hash,
                block_number=recovered.block_number,
            )

        row = build_anchor_row_from_result(receipt.to_anchor_result())
        await deps.writer.upsert(to_asmdb_rows([row])[0])
        _log.info(
            "anchor_written",
            serial=serial,
            tx=receipt.tx_hash.hex() if receipt.tx_hash else None,
            block=receipt.block_number,
        )
        _record_bloom(deps, card)
        return AnchorOutcome(
            serial=serial,
            anchored=True,
            tx_hash=receipt.tx_hash,
            block_number=receipt.block_number,
        )


def _record_bloom(deps: AnchorDependencies, card: Card) -> None:
    """Fire the economic half of the bloom, without ever endangering the anchor row.

    Ordering matters. The anchor row is written *first* and this runs after, because
    the row is the record that the card is on-chain: losing it would send the next run
    back to mint a card the chain already has. Recording the bloom is retryable, so a
    failure here is logged and swallowed rather than propagated — and because the
    anchor row now exists, a later re-run will short-circuit before re-minting.
    """
    if deps.bloom is None:
        return
    try:
        deps.bloom.record_bloom(card.serial, card.rarity, card.happiness)
    except Exception as exc:
        # A dropped bloom is a real hole in the ten-year schedule, so it is loud.
        _log.error("bloom_record_failed", serial=card.serial, error=str(exc))
    else:
        _log.info(
            "bloom_recorded",
            serial=card.serial,
            rarity=card.rarity,
            happiness=card.happiness,
        )


def _build_anchorer(settings: ChainSettings) -> CardAnchorer:
    """Construct the real chain-backed anchorer from the environment."""
    from web3 import HTTPProvider, Web3
    from web3.middleware import ExtraDataToPOAMiddleware

    from app.chain import Anchorer, build_signer

    if not settings.rpc_url:
        raise RuntimeError("CHAIN_RPC_URL must be set to anchor")
    if not settings.card_address:
        raise RuntimeError("CARD_CONTRACT_ADDRESS must be set to anchor")

    web3 = Web3(HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 60}))
    # Polygon is proof-of-authority: its blocks carry a 106-byte extraData where
    # web3.py's default validator insists on 32, so *every* block read raises
    # ExtraDataLengthError without this middleware. The chain layer's own tests run
    # against Anvil, which is not PoA, so this only ever shows up against a real
    # Polygon node.
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return Anchorer(
        web3,
        settings.card_address,
        build_signer(settings),
        chain_id=settings.chain_id,
    )


def _build_bloom_recorder(settings: ChainSettings, anchorer: CardAnchorer) -> BloomRecorder | None:
    """Build the Claim Pool writer, or ``None`` when no pool is configured.

    Returning ``None`` rather than raising keeps anchoring usable on its own: a
    deployment that has cards but no economy yet should still be able to publish
    fingerprints, and the caller treats a missing recorder as "skip the economy".
    """
    from web3 import HTTPProvider, Web3
    from web3.middleware import ExtraDataToPOAMiddleware

    from app.chain import build_signer
    from app.chain.bloom import ClaimPoolWriter

    if not settings.pool_address:
        _log.warning("bloom_recorder_disabled", reason="CLAIM_POOL_ADDRESS is not set")
        return None
    if not settings.rpc_url:
        return None

    del anchorer
    web3 = Web3(HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 60}))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return ClaimPoolWriter(
        web3,
        settings.pool_address,
        build_signer(settings),
        chain_id=settings.chain_id,
    )


async def _run(serials: list[int]) -> None:
    """Anchor each serial in turn, against the real asmDB and the real chain."""
    from app.asmdb import AsmDbClient, AsmDbRepository
    from app.core.config import load_settings
    from app.core.logging import configure_logging
    from app.core.secrets import load_secrets

    settings = load_settings()
    configure_logging(settings.log_level)
    if settings.asmdb_url is None:
        raise RuntimeError("ASMDB_BASE_URL must be set to anchor")

    chain_settings = load_chain_settings()
    anchorer = _build_anchorer(chain_settings)

    secrets = await load_secrets(settings)
    asmdb = AsmDbClient(settings.asmdb_url, secrets.asmdb_bearer_for_client())
    try:
        repository = AsmDbRepository(asmdb)
        deps = AnchorDependencies(
            repository=repository,
            writer=asmdb,
            anchorer=anchorer,
            bloom=_build_bloom_recorder(chain_settings, anchorer),
        )
        targets = serials or await repository.list_card_serials()
        for serial in targets:
            try:
                outcome = await anchor_serial(serial, deps=deps)
            except Exception as exc:
                # One bad serial must not abandon the rest: a catch-up run exists
                # precisely to make progress through a backlog.
                _log.warning("anchor_failed", serial=serial, error=str(exc))
                continue
            _log.info(
                "anchor_outcome",
                serial=outcome.serial,
                anchored=outcome.anchored,
                tx=outcome.tx_hash.hex() if outcome.tx_hash else None,
            )
    finally:
        await asmdb.aclose()


def main(argv: list[str] | None = None) -> None:
    """``python -m app.jobs anchor [SERIAL ...]`` — anchor one or more serials.

    With no serials the job walks every serial asmDB knows about. That is the shape a
    scheduled catch-up wants: :func:`anchor_serial` returns immediately for anything
    already carrying an anchor row, so a full pass costs one cheap read per anchored
    card and actually does work only for the ones still pending.
    """
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(prog="python -m app.jobs anchor")
    parser.add_argument("serials", nargs="*", type=int, help="Serials to anchor.")
    args = parser.parse_args(argv or [])

    asyncio.run(_run(args.serials or _serials_from_environment()))


def _serials_from_environment() -> list[int]:
    """Read ANCHOR_SERIALS ("1 2 3") so a Container Apps Job can select targets."""
    import os

    raw = os.environ.get("ANCHOR_SERIALS", "").replace(",", " ").split()
    return [int(part) for part in raw]
