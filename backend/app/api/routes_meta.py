"""Meta routes: health, collection stats, ERC-721 metadata, and the admin trigger.

Health and stats read straight off the index. ``/api/nft/{serial}`` renders the
ERC-721 document. ``/api/admin/generate`` is the one guarded endpoint: it compares
the ``X-PixelSlime-Admin`` header against the Key Vault token in constant time and,
crucially, never imports or runs the AI pipeline — execution belongs to W8's job.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.serialize import nft_metadata

from .deps import IndexDep, SecretsDep
from .errors import ApiError, error_body
from .params import RarityParam, SerialPath

router = APIRouter(prefix="/api", tags=["meta"])

ADMIN_HEADER = "X-PixelSlime-Admin"


class AdminGenerateBody(BaseModel):
    """Optional knobs for a manual trigger; camelCase on the wire, snake internally."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    force_rarity: RarityParam | None = Field(default=None, alias="forceRarity")
    dry_run: bool = Field(default=False, alias="dryRun")


@router.get("/health")
async def health(index: IndexDep) -> dict[str, Any]:
    """Liveness probe: status, card count and the asmDB engine string."""
    return {
        "status": "degraded" if index.degraded else "ok",
        "cards": index.size,
        "engine": index.engine,
    }


@router.get("/stats")
async def stats(index: IndexDep) -> dict[str, Any]:
    """Collection-wide counters plus the economy projection.

    ``genesisRemaining`` and ``bloomsRemaining`` are *derived* from the in-memory
    card count and the fixed ``docs/PLAN.md`` §8.6 constants — a convenience for the
    UI, not a ledger. The authoritative figures live on-chain and are surfaced once
    W9 lands; treat these as an estimate that can trail the chain by up to one bloom.
    """
    return index.stats()


@router.get("/nft/{serial}")
async def nft(request: Request, index: IndexDep, serial: SerialPath) -> dict[str, Any]:
    """Return the ERC-721 metadata document for a card."""
    card = index.get(serial)
    if card is None:
        raise ApiError(404, "card_not_found", f"No card with serial {serial}")
    return nft_metadata(card, base_url=str(request.base_url))


@router.post("/admin/generate")
async def admin_generate(
    index: IndexDep,
    secrets: SecretsDep,
    admin_token: Annotated[str | None, Header(alias=ADMIN_HEADER)] = None,
    body: AdminGenerateBody | None = None,
) -> JSONResponse:
    """Manually acknowledge a generation request. Off unless the token is configured.

    The header is compared in constant time. When authorised and no card exists for
    today, the request is *accepted* (202) as an acknowledgement — this handler does
    not run the pipeline; W8's Container Apps Job performs the actual generation.
    """
    if not secrets.verify_admin(admin_token):
        return JSONResponse(
            status_code=401,
            content=error_body("unauthorized", "Missing or wrong admin token"),
        )
    if index.today() is not None:
        return JSONResponse(
            status_code=409,
            content=error_body("already_bloomed", "A card already exists for today"),
        )
    payload = body or AdminGenerateBody()
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "dryRun": payload.dry_run,
            "forceRarity": payload.force_rarity,
            "detail": (
                "Trigger acknowledged. The daily job performs generation; "
                "no pipeline runs in this process."
            ),
        },
    )
