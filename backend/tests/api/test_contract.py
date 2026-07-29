"""Contract conformance: the FastAPI app and ``contracts/openapi.yaml`` must agree.

This is the guardrail between W6 and W7. It fails loudly and in **both** directions:
every path+method in the contract must exist in the app, and the app must expose no
``/api`` route the contract does not declare. Drift here breaks W6's generated mock,
so we would rather break this test than integration.
"""

from __future__ import annotations

from collections.abc import Iterator

import yaml
from _api_helpers import OPENAPI_PATH
from starlette.routing import Route

from app.core.config import Settings
from app.main import create_app

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _contract_operations() -> set[tuple[str, str]]:
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    operations: set[tuple[str, str]] = set()
    for path, item in doc["paths"].items():
        for method in item:
            if method.upper() in _HTTP_METHODS:
                operations.add((path, method.upper()))
    return operations


def _flatten_routes(app_routes: list[Route]) -> Iterator[Route]:
    """Yield concrete routes, unwrapping this FastAPI version's lazy included routers."""
    for route in app_routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from original.routes
        else:
            yield route


def _app_api_operations() -> set[tuple[str, str]]:
    app = create_app(Settings(local_dev=True))
    operations: set[tuple[str, str]] = set()
    for route in _flatten_routes(app.routes):
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not path.startswith("/api") or not methods:
            continue
        for method in methods:
            if method in _HTTP_METHODS:
                operations.add((path, method))
    return operations


def test_every_contract_path_is_implemented() -> None:
    missing = _contract_operations() - _app_api_operations()
    assert not missing, f"contract operations not implemented by the app: {sorted(missing)}"


def test_app_declares_no_api_route_absent_from_contract() -> None:
    extra = _app_api_operations() - _contract_operations()
    assert not extra, f"app exposes /api operations absent from the contract: {sorted(extra)}"


def test_contract_declares_the_expected_ten_paths() -> None:
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert len(doc["paths"]) == 10, "the contract is expected to define exactly ten paths"
