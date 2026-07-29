"""Validate every shared contract in this repository.

Run by CI and by anyone who touches `contracts/`. Cheap to run, and it catches the
class of mistake that would otherwise surface three workstreams later as a confusing
runtime error.

Usage:  python scripts/validate_contracts.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"

# From docs/CODEC.md section 3.6 — must match the codec exactly.
TEXT_LIMITS = {
    "name": 18,
    "personality": 90,
    "power_name": 20,
    "power_desc": 90,
    "quote": 40,
}
FORBIDDEN = {"\x00", "\x1f", "\r", "\n"}

failures: list[str] = []


class _StrictLoader(yaml.SafeLoader):
    """YAML loader that refuses duplicate mapping keys.

    PyYAML silently keeps the last value when a key repeats, which is how an
    edit once left two `biome` and two `companion` keys in the Card schema
    without anything complaining. In a file that two workstreams generate code
    from, a silently-dropped key is a contract divergence waiting to happen.
    """


def _no_duplicate_keys(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    dups: list = []
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            dups.append(key)
        seen.add(key)
    if dups:
        raise yaml.YAMLError(f"duplicate keys: {sorted(map(str, dups))}")
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.construct_mapping = _no_duplicate_keys  # type: ignore[method-assign]


def load_yaml_strict(path: Path) -> dict:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        fail(f"{path.name}: {exc}")
        return {}


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"  FAIL  {msg}")


def check_card_schema() -> Draft202012Validator:
    schema = json.loads((CONTRACTS / "card.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    print("  ok    card.schema.json is a valid JSON Schema")
    return Draft202012Validator(schema)


def check_fixtures(validator: Draft202012Validator) -> None:
    fixtures = sorted((CONTRACTS / "cards").glob("*.json"))
    if not fixtures:
        fail("no card fixtures found in contracts/cards/")
        return

    for f in fixtures:
        card = json.loads(f.read_text(encoding="utf-8"))
        for err in sorted(validator.iter_errors(card), key=lambda e: e.path):
            fail(f"{f.name}: {'.'.join(map(str, err.path)) or '<root>'}: {err.message}")

        # The schema cannot express these, but the codec depends on them.
        for field, limit in TEXT_LIMITS.items():
            value = card.get(field, "")
            if len(value) > limit:
                fail(f"{f.name}: {field} is {len(value)} chars, limit is {limit}")
            if bad := FORBIDDEN.intersection(value):
                fail(f"{f.name}: {field} contains forbidden control chars {bad!r}")

        print(f"  ok    {f.name}")


def check_openapi() -> None:
    raw = (CONTRACTS / "openapi.yaml").read_text(encoding="utf-8")
    spec = load_yaml_strict(CONTRACTS / "openapi.yaml")
    version = str(spec.get("openapi", ""))
    if not version.startswith("3.1"):
        fail("openapi.yaml is not OpenAPI 3.1")
    if not spec.get("paths"):
        fail("openapi.yaml declares no paths")

    # `nullable` is OpenAPI 3.0 syntax. Under 3.1 (JSON Schema 2020-12) it is not a
    # keyword at all, so it is silently ignored: a generator emits a non-nullable type
    # and nothing complains. Use `type: [x, "null"]` instead.
    if hits := re.findall(r"^\s*nullable:", raw, re.M):
        fail(f"openapi.yaml uses the 3.0-only `nullable` keyword {len(hits)}x — "
             'under 3.1 it is ignored. Use `type: [x, "null"]`.')

    for name, schema in spec.get("components", {}).get("schemas", {}).items():
        Draft202012Validator.check_schema(schema)
        _ = name

    check_prose_matches_required(spec)
    print(f"  ok    openapi.yaml — {len(spec.get('paths', {}))} paths, no duplicate keys")


def check_prose_matches_required(spec: dict) -> None:
    """A description that promises a field is always present must be backed by `required`.

    This is the exact hole W10 found: `Card.onChain` was documented as "Always present",
    the `required` list omitted it, so `openapi-typescript` generated `onChain?: boolean`.
    The frontend honoured the prose and the backend did not, and because the schema was
    looser than the sentence, nothing caught the disagreement. Prose is not binding —
    only the schema is — so anywhere the two can drift, they must be reconciled here.
    """
    for name, schema in spec.get("components", {}).get("schemas", {}).items():
        required = set(schema.get("required") or [])
        for field, definition in (schema.get("properties") or {}).items():
            description = str(definition.get("description", ""))
            promises = re.search(r"always present", description, re.I)
            if promises and field not in required:
                fail(
                    f"{name}.{field} is documented as always present but is missing from "
                    f"`required` — the schema is looser than its own description"
                )


def check_tokens() -> None:
    tokens = json.loads((CONTRACTS / "design-tokens.json").read_text(encoding="utf-8"))

    rarities = tokens["rarity"]
    total = sum(r["weight"] for r in rarities.values())
    if abs(total - 1.0) > 1e-9:
        fail(f"rarity weights sum to {total}, not 1.0")

    card = tokens["card"]
    for dim in ("width", "height", "thumbWidth", "thumbHeight"):
        if card[dim] % 16:
            fail(f"card.{dim} = {card[dim]} is not divisible by 16 — gpt-image-2 will reject it")

    if len(tokens["type"]) != 16:
        fail(f"{len(tokens['type'])} types declared, the codec packs exactly 16 into 4 bits")

    print(f"  ok    design-tokens.json — weights sum to 1.0, {len(tokens['type'])} types")


def check_dictionary() -> None:
    d = ROOT / "assets" / "psdict_v1.bin"
    if not d.exists():
        fail("assets/psdict_v1.bin is missing — run scripts/build_dict.py")
        return
    size = d.stat().st_size
    if size > 32768:
        fail(f"dictionary is {size} bytes, zlib's window is 32768")
    print(f"  ok    psdict_v1.bin — {size:,} bytes")


def main() -> int:
    print("contracts:")
    validator = check_card_schema()
    check_fixtures(validator)
    check_openapi()
    check_tokens()
    check_dictionary()

    print()
    if failures:
        print(f"{len(failures)} problem(s) found")
        return 1
    print("all contracts valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
