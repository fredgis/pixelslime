"""The URLs an NFT marketplace will actually fetch.

An ERC-721 `tokenURI` and the metadata it returns are consumed by software we do not
control, on a chain we cannot edit after the fact. Two things therefore have to be
right the first time, and neither is visible from inside the app:

* the URI must address the **metadata** document, not the card API;
* every URL must be **https**, because the app sits behind a TLS-terminating proxy
  and an unwrapped `request.base_url` reports the internal http scheme.

Both were wrong for PS-0001, whose `tokenURI` is now permanently baked into the chain.
"""

from __future__ import annotations

from _api_helpers import build_card

from app.core.serialize import nft_metadata
from app.jobs.anchor import DEFAULT_TOKEN_URI_BASE


def test_the_token_uri_base_addresses_the_metadata_document() -> None:
    # PS-0001 was minted with https://pixelslime.cloud/api/cards/1 — the *card* API on
    # the apex host. A marketplace following it gets the card payload rather than
    # ERC-721 metadata, and the apex was not even bound at the time. That URI cannot
    # be changed now, so the only thing to protect is every card after it.
    assert DEFAULT_TOKEN_URI_BASE.endswith("/api/nft/")
    assert DEFAULT_TOKEN_URI_BASE.startswith("https://")


def test_metadata_urls_are_https_even_behind_a_proxy() -> None:
    # Uvicorn sees http:// from the ingress. Anything echoing that back produces
    # mixed content a marketplace or browser may simply refuse to load.
    card = build_card(1)
    meta = nft_metadata(card, base_url="http://www.pixelslime.cloud/")

    assert str(meta["image"]).startswith("https://")
    assert str(meta["external_url"]).startswith("https://")


def test_an_https_base_url_is_left_alone() -> None:
    card = build_card(1)
    meta = nft_metadata(card, base_url="https://www.pixelslime.cloud/")
    assert str(meta["image"]) == "https://www.pixelslime.cloud/api/cards/1/image"


def test_a_local_http_base_url_is_not_forced() -> None:
    # Forcing https on localhost would break local development and the test client,
    # so the upgrade applies only to real hosts.
    card = build_card(1)
    meta = nft_metadata(card, base_url="http://localhost:8000/")
    assert str(meta["image"]).startswith("http://localhost:8000/")
