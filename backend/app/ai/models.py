"""Typed card models mirroring ``contracts/card.schema.json``.

The pipeline returns a plain ``dict`` (the schema is the shared truth for W2/W7),
but it is assembled and validated *through* these Pydantic models so an invalid
card can never leave this package. The constraints here mirror the contract
exactly; a drift test (``tests/ai/test_models.py``) asserts they stay in sync.

``type`` is exposed under a ``card_type`` attribute with alias ``"type"`` to avoid
shadowing the builtin while still round-tripping the correct JSON key.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RarityName = Literal["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC"]
CardTypeName = Literal[
    "FAIRY",
    "FOREST",
    "WATER",
    "EMBER",
    "STORM",
    "STONE",
    "SUGAR",
    "GHOST",
    "METAL",
    "COSMIC",
    "BLOOM",
    "FROST",
    "SLUDGE",
    "BEAM",
    "PAPER",
    "DREAM",
]

_NO_CONTROL = r"^[^\x00\x1f\r\n]+$"


class Flags(BaseModel):
    """The card ``flags`` sub-object (all default to ``False``)."""

    model_config = ConfigDict(extra="forbid")

    has_companion: bool = False
    has_accessory: bool = False
    verified: bool = False
    on_chain: bool = False
    seed: bool = False


class Card(BaseModel):
    """A full PixelSlime card, validated against the contract's constraints."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    series: Literal["PS"] = "PS"
    serial: int = Field(ge=1, le=65535)

    name: str = Field(min_length=1, max_length=18, pattern=_NO_CONTROL)
    level: int = Field(ge=1, le=100)
    rarity: RarityName
    card_type: CardTypeName = Field(alias="type")

    height_mm: int = Field(ge=1, le=65535)
    weight_g: int = Field(ge=1, le=65535)

    strength: int = Field(ge=0, le=100)
    endurance: int = Field(ge=0, le=100)
    agility: int = Field(ge=0, le=100)
    happiness: int = Field(ge=0, le=100)

    art_id: int = Field(ge=0, le=255)
    style_id: int = Field(ge=0, le=255)
    frame_id: int = Field(ge=0, le=255)
    background_id: int = Field(ge=0, le=255)
    biome_id: int = Field(ge=0, le=255)
    mood_id: int = Field(ge=0, le=255)

    personality: str = Field(min_length=1, max_length=90, pattern=_NO_CONTROL)
    power_name: str = Field(min_length=1, max_length=20, pattern=_NO_CONTROL)
    power_desc: str = Field(min_length=1, max_length=90, pattern=_NO_CONTROL)
    quote: str = Field(min_length=1, max_length=40, pattern=_NO_CONTROL)

    mint_day: int = Field(ge=0, le=65535)
    shiny: bool = False
    flags: Flags = Field(default_factory=Flags)

    art_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{8}$")

    biome: str | None = Field(default=None, max_length=40)
    companion: str | None = Field(default=None, max_length=40)

    def to_card_dict(self) -> dict[str, object]:
        """Return the plain dict shape shared with W2/W7 (``type`` key, no nulls)."""
        return self.model_dump(by_alias=True, exclude_none=True)
