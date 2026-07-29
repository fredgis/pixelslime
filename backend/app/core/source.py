"""The card *source* behind the index — the only thing that talks to asmDB.

The read API never touches asmDB directly; it reads the in-memory index. That
index is *built* and *reconciled* from a :class:`CardSource`. Hiding asmDB behind
this small protocol does two things:

* it keeps the codec ↔ asmDB row conversion in exactly one place, and
* it lets the whole backend run against an in-memory fake (tests, local dev) that
  honours the same 175-byte / no-NUL-CR-LF row rules asmDB enforces, so a green
  test suite means something.

The production adapter wraps W3's :class:`~app.asmdb.AsmDbClient` /
:class:`~app.asmdb.AsmDbRepository`; nothing in W3 is modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.asmdb import AsmDbClient, AsmDbNotFound, AsmDbRepository, AsmDbStarting
from app.asmdb import Row as AsmDbRow
from app.codec import Card, Row, decode, encode

_MAX_CONTENT_BYTES = 175
_FORBIDDEN_BYTES = (0x00, 0x0D, 0x0A)


@dataclass(frozen=True)
class SourceHealth:
    """The two facts ``/api/health`` needs from the store: liveness and engine."""

    ok: bool
    engine: str


@runtime_checkable
class CardSource(Protocol):
    """A read view over persisted cards, deliberately narrow.

    Everything here is off the hot path: it is called at startup and by the
    background reconcile loop, never while serving a gallery request.
    """

    async def health(self) -> SourceHealth:
        """Probe the store; raise if it is unreachable or still starting."""
        ...

    async def list_serials(self) -> list[int]:
        """Return every card serial the store holds (a deliberate header scan)."""
        ...

    async def read_card(self, serial: int) -> Card:
        """Read and decode one card. Raise :class:`AsmDbNotFound` if absent."""
        ...

    async def card_for_date(self, yyyymmdd_value: int) -> Card | None:
        """Return the card whose header date equals ``yyyymmdd_value``, or ``None``."""
        ...

    async def aclose(self) -> None:
        """Release any transport the source owns."""
        ...


def _to_codec_rows(rows: list[AsmDbRow]) -> list[Row]:
    """Project asmDB rows onto codec rows so :func:`app.codec.decode` can run.

    The two ``Row`` models are structurally identical over the four columns the
    codec cares about; asmDB additionally carries engine timestamps the decoder
    neither needs nor trusts.
    """
    return [Row(id=row.id, value=row.value, tag=row.tag, content=row.content) for row in rows]


class AsmDbCardSource:
    """Adapt W3's asmDB client to :class:`CardSource`. Owns nothing but the wrap."""

    def __init__(self, client: AsmDbClient) -> None:
        self._client = client
        self._repo = AsmDbRepository(client)

    async def health(self) -> SourceHealth:
        health = await self._client.health()
        return SourceHealth(ok=True, engine=health.engine)

    async def list_serials(self) -> list[int]:
        return await self._repo.list_card_serials()

    async def read_card(self, serial: int) -> Card:
        rows = await self._repo.read_card_rows(serial)
        return decode(_to_codec_rows(rows))

    async def card_for_date(self, yyyymmdd_value: int) -> Card | None:
        try:
            header = await self._repo.find_card_by_date(yyyymmdd_value)
        except AsmDbNotFound:
            return None
        return await self.read_card(header.id // 16)

    async def aclose(self) -> None:
        await self._client.aclose()


def _guard_row_content(content: str) -> None:
    """Reject anything asmDB would reject, so the fake cannot be more lenient."""
    encoded = content.encode("utf-8")
    if len(encoded) > _MAX_CONTENT_BYTES:
        raise ValueError(
            f"row content is {len(encoded)} bytes, over asmDB's {_MAX_CONTENT_BYTES}-byte limit"
        )
    if any(byte in encoded for byte in _FORBIDDEN_BYTES):
        raise ValueError("row content contains a NUL, CR or LF byte")


class InMemoryCardSource:
    """An in-memory stand-in for asmDB that stores real PSC-1 rows.

    Cards are held as the exact codec rows asmDB would store — validated against
    the byte rules on insert — and decoded on read, so a round-trip through this
    fake exercises the same encode/decode path production does.
    """

    def __init__(self, *, engine: str = "asmdb-fake/1.0", awake: bool = True) -> None:
        self._rows: dict[int, list[Row]] = {}
        self._engine = engine
        #: Flip to ``False`` to simulate a scaled-to-zero instance for tests.
        self.awake = awake

    def add_card(self, card: Card) -> None:
        """Encode and store a card, enforcing asmDB's content rules."""
        rows = encode(card)
        for row in rows:
            _guard_row_content(row.content)
        self._rows[card.serial] = rows

    def add_partial_card(self, card: Card, *, keep_rows: int) -> list[Row]:
        """Store only the first ``keep_rows`` rows of a multi-row card.

        Simulates the wreckage a crash mid-write can leave behind — the header row
        (part 0) is present, so the serial is discoverable by a header scan, but a
        continuation row is missing and the stream cannot be reassembled. W3's
        ``write_card_rows`` is meant to prevent this, but the index must survive it
        regardless. Returns the *full* row set so a test can assert what was dropped.
        """
        rows = encode(card)
        self._rows[card.serial] = rows[:keep_rows]
        return rows

    def remove(self, serial: int) -> None:
        self._rows.pop(serial, None)

    async def health(self) -> SourceHealth:
        if not self.awake:
            raise AsmDbStarting("fake asmDB instance is starting", code="instance_starting")
        return SourceHealth(ok=True, engine=self._engine)

    async def list_serials(self) -> list[int]:
        if not self.awake:
            raise AsmDbStarting("fake asmDB instance is starting", code="instance_starting")
        return sorted(self._rows)

    async def read_card(self, serial: int) -> Card:
        rows = self._rows.get(serial)
        if rows is None:
            raise AsmDbNotFound(f"no card with serial {serial}", code="not_found", status_code=404)
        return decode(rows)

    async def card_for_date(self, yyyymmdd_value: int) -> Card | None:
        for rows in self._rows.values():
            if rows[0].value == yyyymmdd_value:
                return decode(rows)
        return None

    async def aclose(self) -> None:
        return None
