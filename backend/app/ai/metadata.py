"""Step 2 of the pipeline: the copywriter — gpt-5.6-sol via Structured Outputs.

The model writes only the *creative and numeric* fields (name, personality,
power, quote, level, height, weight, the four stats). The discrete gameplay
enums (rarity, type) are never left to it — they come from the roll.

Strict Structured Outputs guarantees the JSON *shape* but not string lengths or
integer ranges (``maxLength``/``minimum`` are not enforced by the model), so this
module validates every field against ``docs/CODEC.md`` §3.6 and
``contracts/card.schema.json`` itself, and on any violation it re-asks the model
to fix it — up to two retries. It never truncates: a card that will not fit the
codec is a hard error, because a silently shortened caption would then disagree
with the text painted on the image.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from ._chat import json_schema_format, request_structured
from .config import (
    FORBIDDEN_TEXT_CHARS,
    HEIGHT_MM_RANGE,
    LEVEL_RANGE,
    STAT_RANGE,
    TEXT_BYTE_LIMITS,
    TEXT_CHAR_LIMITS,
    TEXT_MODEL,
    WEIGHT_G_RANGE,
)
from .errors import MetadataError, MetadataValidationError
from .prompt import MasterPrompt
from .roll import Roll

#: The five DEFLATE-bundled text fields, in codec order (docs/CODEC.md §3.5).
_TEXT_FIELDS: tuple[str, ...] = ("name", "personality", "power_name", "power_desc", "quote")
_STAT_FIELDS: tuple[str, ...] = ("strength", "endurance", "agility", "happiness")

_FORBIDDEN_LABELS = {
    "\x1f": "a unit-separator",
    "\x00": "a NUL",
    "\r": "a carriage return",
    "\n": "a newline",
}

MAX_RETRIES = 2


@dataclass(frozen=True, slots=True)
class CardText:
    """The model-written portion of a card, validated and codec-safe."""

    name: str
    level: int
    height_mm: int
    weight_g: int
    strength: int
    endurance: int
    agility: int
    happiness: int
    personality: str
    power_name: str
    power_desc: str
    quote: str


def _metadata_schema() -> dict[str, Any]:
    """Strict JSON Schema for the model-written fields.

    Length and range limits are intentionally expressed only in the *field
    descriptions* (not as ``maxLength``/``minimum``): strict Structured Outputs
    rejects those keywords, and they would be advisory anyway — the hard
    enforcement is ``_validate`` below.
    """

    def string(desc: str) -> dict[str, str]:
        return {"type": "string", "description": desc}

    def integer(desc: str) -> dict[str, str]:
        return {"type": "integer", "description": desc}

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": string("Unique, fun slime name. At most 18 characters."),
            "level": integer("Level from 1 to 100 inclusive."),
            "height_mm": integer(
                "Height in millimetres, 1-65535; plausible for a tiny slime (e.g. 150-500)."
            ),
            "weight_g": integer(
                "Weight in grams, 1-65535; plausible for a tiny slime (e.g. 300-3000)."
            ),
            "strength": integer("0 to 100 inclusive."),
            "endurance": integer("0 to 100 inclusive."),
            "agility": integer("0 to 100 inclusive."),
            "happiness": integer("0 to 100 inclusive."),
            "personality": string(
                "One or two short sentences of personality. At most 90 characters."
            ),
            "power_name": string("Short power name. At most 20 characters."),
            "power_desc": string("One short sentence describing the power. At most 90 characters."),
            "quote": string("A short spoken line from the slime. At most 40 characters."),
        },
        "required": [
            "name",
            "level",
            "height_mm",
            "weight_g",
            *_STAT_FIELDS,
            "personality",
            "power_name",
            "power_desc",
            "quote",
        ],
    }


def _system_message(master_prompt: MasterPrompt) -> str:
    return (
        "You are the copywriter for PixelSlime collectible trading cards. "
        "Below is the master card brief for context on the universe, tone and the "
        "fields a card shows. Write ONLY the requested JSON for one card. All text "
        "is in ENGLISH. Respect every character limit exactly — text over the limit "
        "cannot be stored and will be rejected. Never use newlines inside a field.\n\n"
        "=== MASTER BRIEF ===\n"
        f"{master_prompt.text}"
    )


def _user_message(roll: Roll, used_names: Sequence[str]) -> str:
    companion = roll.companion if roll.has_companion else "none"
    accessory = roll.accessory if roll.has_accessory else "none"
    used = ", ".join(used_names) if used_names else "(none yet)"
    return (
        "ROLLED ATTRIBUTES (authoritative — write text that fits these, do not "
        "restate or change them):\n"
        f"- rarity: {roll.rarity}\n"
        f"- type: {roll.card_type}\n"
        f"- biome / scene: {roll.biome}\n"
        f"- mood: {roll.mood}\n"
        f"- companion: {companion}\n"
        f"- accessory: {accessory}\n"
        f"- shiny: {str(roll.shiny).lower()}\n\n"
        "WRITE THESE FIELDS (respect the limits):\n"
        "- name (<=18 chars), level (1-100)\n"
        "- height_mm (1-65535), weight_g (1-65535)\n"
        "- strength, endurance, agility, happiness (each 0-100)\n"
        "- personality (<=90 chars), power_name (<=20 chars), power_desc (<=90 chars)\n"
        "- quote (<=40 chars)\n\n"
        f"NAMES ALREADY USED — pick a different, unused name:\n{used}"
    )


def _field_problems(field: str, value: str) -> list[str]:
    problems: list[str] = []
    char_limit = TEXT_CHAR_LIMITS[field]
    byte_limit = TEXT_BYTE_LIMITS[field]
    n_chars = len(value)
    n_bytes = len(value.encode("utf-8"))
    if n_chars == 0:
        problems.append(f"'{field}' is empty; it must have at least 1 character.")
    if n_chars > char_limit:
        problems.append(f"'{field}' is {n_chars} characters; shorten it to at most {char_limit}.")
    if n_bytes > byte_limit:
        problems.append(
            f"'{field}' is {n_bytes} UTF-8 bytes; shorten it to at most {byte_limit} bytes."
        )
    for bad in FORBIDDEN_TEXT_CHARS:
        if bad in value:
            problems.append(f"'{field}' contains {_FORBIDDEN_LABELS[bad]} character; remove it.")
    return problems


def _range_problem(field: str, value: int, low: int, high: int) -> list[str]:
    if not low <= value <= high:
        return [f"'{field}' is {value}; it must be between {low} and {high} inclusive."]
    return []


def _validate(data: dict[str, Any], used_names: Sequence[str]) -> list[str]:
    """Return a list of explicit, human-readable problems (empty == valid)."""
    problems: list[str] = []

    for field in _TEXT_FIELDS:
        value = data.get(field)
        if not isinstance(value, str):
            problems.append(f"'{field}' is missing or not a string.")
            continue
        problems.extend(_field_problems(field, value))

    name = data.get("name")
    if isinstance(name, str):
        used_folded = {u.casefold() for u in used_names}
        if name.casefold() in used_folded:
            problems.append(f"the name {name!r} is already used; choose a different, unused name.")

    for field, (low, high) in (
        ("level", LEVEL_RANGE),
        ("height_mm", HEIGHT_MM_RANGE),
        ("weight_g", WEIGHT_G_RANGE),
        *((stat, STAT_RANGE) for stat in _STAT_FIELDS),
    ):
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            problems.append(f"'{field}' is missing or not an integer.")
            continue
        problems.extend(_range_problem(field, value, low, high))

    return problems


def _correction_message(problems: list[str]) -> str:
    bullet = "\n".join(f"- {p}" for p in problems)
    return (
        "Your previous JSON had these problems. Fix ALL of them and return only the "
        "corrected JSON, keeping every other field within its limit:\n"
        f"{bullet}"
    )


async def generate_metadata(
    roll: Roll,
    used_names: Sequence[str],
    *,
    client: httpx.AsyncClient,
    master_prompt: MasterPrompt,
    max_retries: int = MAX_RETRIES,
) -> CardText:
    """Ask gpt-5.6-sol to write the card text, validating and retrying on failure.

    On each failure the exact problems are fed back to the model with an explicit
    instruction to shorten/fix; after ``max_retries`` further attempts a
    ``MetadataValidationError`` is raised rather than truncating anything.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_message(master_prompt)},
        {"role": "user", "content": _user_message(roll, used_names)},
    ]
    schema = _metadata_schema()
    last_problems: list[str] = []

    for attempt in range(max_retries + 1):
        body = {
            "model": TEXT_MODEL,
            "messages": messages,
            "response_format": json_schema_format("pixelslime_card_text", schema),
        }
        content = await request_structured(client, body, error_cls=MetadataError)
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            problems = [f"the response was not valid JSON: {exc}"]
            data = {}
        else:
            problems = _validate(data, used_names)

        if not problems:
            return CardText(
                name=data["name"],
                level=data["level"],
                height_mm=data["height_mm"],
                weight_g=data["weight_g"],
                strength=data["strength"],
                endurance=data["endurance"],
                agility=data["agility"],
                happiness=data["happiness"],
                personality=data["personality"],
                power_name=data["power_name"],
                power_desc=data["power_desc"],
                quote=data["quote"],
            )

        last_problems = problems
        if attempt < max_retries:
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": _correction_message(problems)})

    raise MetadataValidationError(
        f"card text still invalid after {max_retries + 1} attempts",
        problems=last_problems,
    )
