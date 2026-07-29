"""SPA hosting: real files, history fallback, and never swallowing /api."""

from __future__ import annotations

from pathlib import Path

from _api_helpers import load_fixture_card
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.secrets import SecretProvider
from app.core.source import InMemoryCardSource
from app.main import create_app
from app.storage.blob import InMemoryBlobStore

INDEX_HTML = "<!doctype html><html><body><div id='root'>SLIMEDEX</div></body></html>"


def _client_with_dist(dist: Path) -> TestClient:
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('hi')", encoding="utf-8")

    source = InMemoryCardSource()
    source.add_card(load_fixture_card("mochibo"))
    blob = InMemoryBlobStore()
    blob.seed_card(1, b"PNG-1", b"WEBP-1")
    settings = Settings(local_dev=True, frontend_dist=str(dist))
    secrets = SecretProvider(asmdb_bearer=None, admin_token=None)
    return TestClient(create_app(settings, source=source, blob=blob, secrets=secrets))


def test_root_serves_index_html(tmp_path: Path) -> None:
    with _client_with_dist(tmp_path) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "SLIMEDEX" in response.text


def test_client_route_falls_back_to_index(tmp_path: Path) -> None:
    with _client_with_dist(tmp_path) as client:
        response = client.get("/slime/42")
        assert response.status_code == 200
        assert "SLIMEDEX" in response.text


def test_real_asset_is_served(tmp_path: Path) -> None:
    with _client_with_dist(tmp_path) as client:
        response = client.get("/assets/app.js")
        assert response.status_code == 200
        assert "console.log" in response.text


def test_api_routes_are_not_swallowed(tmp_path: Path) -> None:
    with _client_with_dist(tmp_path) as client:
        assert client.get("/api/cards").status_code == 200
        assert client.get("/api/cards").json()["total"] == 1


def test_unknown_api_route_is_json_404_not_index(tmp_path: Path) -> None:
    with _client_with_dist(tmp_path) as client:
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["error"]["code"] == "not_found"


def test_missing_dist_is_tolerated(tmp_path: Path) -> None:
    # No index.html written → no SPA route, but the API must still work.
    source = InMemoryCardSource()
    blob = InMemoryBlobStore()
    settings = Settings(local_dev=True, frontend_dist=str(tmp_path / "nope"))
    secrets = SecretProvider(asmdb_bearer=None, admin_token=None)
    with TestClient(create_app(settings, source=source, blob=blob, secrets=secrets)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 404
