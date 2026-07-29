"""Shared query/path parameter types for the API.

The enums are declared here as ``Literal`` aliases so FastAPI emits the same enum
schema the contract does *and* returns 422 on an out-of-range value. A guard at
import time asserts they still match the codec's own tuples, so a future change to
the codec that silently diverges from ``contracts/openapi.yaml`` fails loudly here
rather than at integration time with W6.
"""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from fastapi import Path, Query

from app.codec import RARITIES, TYPES

RarityParam = Literal["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC"]
SlimeTypeParam = Literal[
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
SortParam = Literal["newest", "oldest", "rarest", "happiest"]

#: The lowest and highest card serials the contract allows on the path.
SERIAL_MIN = 1
SERIAL_MAX = 65535

#: Path parameter for a card serial, validated to the contract's 1..65535 range.
SerialPath = Annotated[int, Path(ge=SERIAL_MIN, le=SERIAL_MAX)]

#: Gallery query parameters, each carrying the contract's bounds/defaults.
PageParam = Annotated[int, Query(ge=1)]
SizeParam = Annotated[int, Query(ge=1, le=100)]
TypeParam = Annotated[SlimeTypeParam | None, Query(alias="type")]
RarityQueryParam = Annotated[RarityParam | None, Query()]
SortQueryParam = Annotated[SortParam, Query()]
SearchParam = Annotated[str | None, Query(max_length=40)]


def _assert_matches() -> None:
    """Fail import if the API enums drift from the codec's canonical tuples."""
    if set(get_args(RarityParam)) != set(RARITIES):
        raise RuntimeError("RarityParam is out of sync with app.codec.RARITIES")
    if set(get_args(SlimeTypeParam)) != set(TYPES):
        raise RuntimeError("SlimeTypeParam is out of sync with app.codec.TYPES")


_assert_matches()
