"""The ``Card`` domain model and the ``Row`` asmDB record, as Pydantic v2 models.

``Card`` mirrors ``contracts/card.schema.json`` for exactly the fields PSC-1
carries. Two schema fields are deliberately **not** modelled as card state:
``biome`` and ``companion`` are documented in the schema itself as display-only
labels resolved client-side from ``biome_id``/``mood_id`` and are explicitly "NOT
encoded in PSC-1". Because they cannot be recovered from the stream, keeping them
would make ``decode(encode(card)) == card`` impossible; instead they are accepted
and dropped at construction so the fixtures load while every *other* unknown key
still fails loudly under ``extra="forbid"``.

Field length limits here are the schema's **character** limits. The stricter
UTF-8 **byte** limits from ``docs/CODEC.md`` §3.6 are enforced at encode time,
because a character may be up to four bytes and so a char-valid field can still
overflow the byte budget.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, get_args

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .errors import CompanionError

Rarity = Literal["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC"]
# fmt: off
SlimeType = Literal[
    "FAIRY", "FOREST", "WATER", "EMBER", "STORM", "STONE", "SUGAR", "GHOST",
    "METAL", "COSMIC", "BLOOM", "FROST", "SLUDGE", "BEAM", "PAPER", "DREAM",
]
# fmt: on

# Frozen ordinals — these indices are the on-wire enum values. Never reorder.
RARITIES: tuple[str, ...] = get_args(Rarity)
TYPES: tuple[str, ...] = get_args(SlimeType)

_FORBIDDEN = ("\x00", "\x1f", "\r", "\n")


def _no_control(value: str) -> str:
    """Reject the four bytes that neither asmDB nor the field separator tolerate."""
    for bad in _FORBIDDEN:
        if bad in value:
            raise ValueError(f"field contains forbidden control character {bad!r}")
    return value


_Name = Annotated[str, Field(min_length=1, max_length=18), AfterValidator(_no_control)]
_Personality = Annotated[str, Field(min_length=1, max_length=90), AfterValidator(_no_control)]
_PowerName = Annotated[str, Field(min_length=1, max_length=20), AfterValidator(_no_control)]
_PowerDesc = Annotated[str, Field(min_length=1, max_length=90), AfterValidator(_no_control)]
_Quote = Annotated[str, Field(min_length=1, max_length=40), AfterValidator(_no_control)]


class Flags(BaseModel):
    """The five semantic bits packed into the header ``flags`` word (§3.3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_companion: bool = False
    has_accessory: bool = False
    verified: bool = False
    on_chain: bool = False
    seed: bool = False


class Card(BaseModel):
    """A PixelSlime card, restricted to the fields PSC-1 serialises."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    series: Literal["PS"] = "PS"
    serial: int = Field(ge=1, le=65535)
    name: _Name
    level: int = Field(ge=1, le=100)
    rarity: Rarity
    type: SlimeType  # 'type' mirrors the schema field name verbatim
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
    personality: _Personality
    power_name: _PowerName
    power_desc: _PowerDesc
    quote: _Quote
    mint_day: int = Field(ge=0, le=65535)
    shiny: bool = False
    flags: Flags = Field(default_factory=Flags)
    companion_id: int = Field(default=0, ge=0, le=63)
    art_sha: str = Field(default="00000000", pattern=r"^[0-9a-f]{8}$")

    @model_validator(mode="before")
    @classmethod
    def _drop_display_only(cls, data: Any) -> Any:
        """Accept-and-drop the schema's two display-only fields (see module docstring)."""
        if isinstance(data, dict) and ("biome" in data or "companion" in data):
            return {k: v for k, v in data.items() if k not in ("biome", "companion")}
        return data

    @model_validator(mode="after")
    def _companion_id_requires_flag(self) -> Card:
        """Enforce §3.3: ``companion_id`` must be 0 unless ``flags.has_companion`` is set.

        Raises :class:`CompanionError` rather than silently zeroing, so a caller that
        forgot to set the flag learns about it instead of losing the companion.
        """
        if self.companion_id and not self.flags.has_companion:
            raise CompanionError(
                f"companion_id is {self.companion_id} but has_companion is false; "
                "it must be 0 when the card carries no companion (§3.3)"
            )
        return self


class Row(BaseModel):
    """One asmDB record: ``id`` and ``value`` are integers here; the asmDB layer is
    responsible for rendering them as JSON strings (a u64 does not survive JS)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int  # 'id' mirrors the asmDB column name verbatim
    value: int
    tag: str
    content: str
