"""Tests for the guarded ``/api/admin/generate`` trigger."""

from __future__ import annotations

from _api_helpers import ClientFactory, build_card, card_minted_today

ADMIN_TOKEN = "s3cr3t-admin-token"
HEADER = "X-PixelSlime-Admin"


def test_rejected_without_header(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[], admin_token=ADMIN_TOKEN)
    response = client.post("/api/admin/generate")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_rejected_with_wrong_token(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[], admin_token=ADMIN_TOKEN)
    response = client.post("/api/admin/generate", headers={HEADER: "nope"})
    assert response.status_code == 401


def test_accepted_with_correct_token(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[], admin_token=ADMIN_TOKEN)
    response = client.post("/api/admin/generate", headers={HEADER: ADMIN_TOKEN})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["dryRun"] is False


def test_dry_run_is_accepted(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[], admin_token=ADMIN_TOKEN)
    response = client.post(
        "/api/admin/generate", headers={HEADER: ADMIN_TOKEN}, json={"dryRun": True}
    )
    assert response.status_code == 202
    assert response.json()["dryRun"] is True


def test_conflict_when_today_already_bloomed(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(
        cards=[card_minted_today(serial=1)], admin_token=ADMIN_TOKEN
    )
    response = client.post("/api/admin/generate", headers={HEADER: ADMIN_TOKEN})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_bloomed"


def test_disabled_when_no_token_configured(make_client: ClientFactory) -> None:
    # No admin token configured ⇒ endpoint is off ⇒ even a header is rejected.
    client, _source, _blob = make_client(cards=[build_card(1, mint_day=5)], admin_token=None)
    response = client.post("/api/admin/generate", headers={HEADER: "anything"})
    assert response.status_code == 401
