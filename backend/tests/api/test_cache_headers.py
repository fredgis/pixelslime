"""Caching rules: what may be reused, what must never be.

These tests exist because the site once served no ``Cache-Control`` at all, and the
consequence was the opposite of what anyone would have chosen: browsers applied
heuristic freshness to the hashed bundles (which can safely be kept for a year) while
nothing stopped a cache from holding on to ``/api/cards/today`` - the one response that
is wrong tomorrow. A visitor could refresh repeatedly and keep being shown the previous
day's slime, with no request ever reaching the server.

The rule is therefore asserted per surface rather than "a header is present": it is the
*direction* that was broken, not the presence.
"""

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

IMMUTABLE = "public, max-age=31536000, immutable"


def _client(dist: Path) -> TestClient:
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "app-Ba3x9.js").write_text("console.log('hi')", encoding="utf-8")

    source = InMemoryCardSource()
    source.add_card(load_fixture_card("mochibo"))
    blob = InMemoryBlobStore()
    blob.seed_card(1, b"PNG-1", b"WEBP-1")
    settings = Settings(local_dev=True, frontend_dist=str(dist))
    secrets = SecretProvider(asmdb_bearer=None, admin_token=None)
    return TestClient(create_app(settings, source=source, blob=blob, secrets=secrets))


def test_todays_card_is_never_stored(tmp_path: Path) -> None:
    """The regression that started all this: yesterday's slime, served from a cache.

    Asserted whatever the status code, because the 404 served between midnight and
    10:00 Paris is exactly as dangerous to cache as the card itself - holding on to it
    would hide the bloom for the rest of the day.
    """
    with _client(tmp_path) as client:
        assert client.get("/api/cards/today").headers["cache-control"] == "no-store"


def test_daily_json_is_never_stored(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        for path in ("/api/cards", "/api/cards/1", "/api/stats", "/api/health"):
            assert client.get(path).headers["cache-control"] == "no-store", path


def test_card_media_is_cached_hard(tmp_path: Path) -> None:
    """A minted card's pixels are committed on-chain, so they cannot change.

    Worth caching rather than merely safe to: these are ~2 MB PNGs, and re-fetching
    one on every navigation is the difference between a gallery that feels instant and
    one that does not.
    """
    with _client(tmp_path) as client:
        for path in ("/api/cards/1/image", "/api/cards/1/thumb"):
            assert client.get(path).headers["cache-control"] == IMMUTABLE, path


def test_hashed_assets_are_cached_hard(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/assets/app-Ba3x9.js")
        assert response.status_code == 200
        assert response.headers["cache-control"] == IMMUTABLE


def test_index_is_always_revalidated(tmp_path: Path) -> None:
    """index.html names the hashed bundles, so a stale copy boots a build that is gone.

    Checked on a deep client route as well: they all fall back to the same document,
    and a rule that only held for ``/`` would leave every bookmarked page behind.
    """
    with _client(tmp_path) as client:
        for path in ("/", "/dex", "/card/1"):
            assert client.get(path).headers["cache-control"] == "no-cache", path
