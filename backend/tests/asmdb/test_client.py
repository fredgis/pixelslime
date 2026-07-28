"""Behavioural tests for the asmDB HTTP boundary."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
import pytest
import respx
from pydantic import ValidationError

from app.asmdb import (
    AsmDbClient,
    AsmDbError,
    AsmDbNotFound,
    AsmDbRateLimited,
    AsmDbUnauthorized,
    AsmDbValidationError,
    Row,
)

BASE_URL = "https://asmdb.example/db/unit-instance"
TEST_CREDENTIAL = "unit-test-credential"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def wire_row(
    row_id: int,
    value: int,
    tag: str,
    content: str,
    *,
    created: int = 1_785_001_293_764,
    updated: int = 1_785_001_293_764,
) -> dict[str, str]:
    """Build the exact string-integer shape emitted by the Go sidecar."""
    return {
        "id": str(row_id),
        "value": str(value),
        "tag": tag,
        "content": content,
        "created": str(created),
        "updated": str(updated),
    }


def client(*, retry_attempts: int = 3) -> AsmDbClient:
    """Keep retry tests fast while exercising the real tenacity path."""
    return AsmDbClient(
        BASE_URL,
        TEST_CREDENTIAL,
        retry_attempts=retry_attempts,
        retry_min_wait=0,
        retry_max_wait=0,
    )


@respx.mock
async def test_happy_paths_convert_row_numbers_and_send_string_payloads() -> None:
    health_route = respx.get(f"{BASE_URL}/health").mock(
        return_value=httpx.Response(
            200,
            json={
                "engine": "1.7.0",
                "rows": 1,
                "status": "ok",
                "storageFormat": "2",
            },
        )
    )
    get_route = respx.get(f"{BASE_URL}/v1/rows/16").mock(
        return_value=httpx.Response(
            200,
            json={"row": wire_row(16, 20_260_728, "psc.1.0", "payload")},
        )
    )
    insert_route = respx.post(f"{BASE_URL}/v1/rows").mock(
        return_value=httpx.Response(
            201,
            json={"row": wire_row(17, -17, "psc.1.1", "next")},
        )
    )
    update_route = respx.put(f"{BASE_URL}/v1/rows/17").mock(
        return_value=httpx.Response(
            200,
            json={"row": wire_row(17, -17, "psc.1.1", "updated", updated=1_785_001_293_999)},
        )
    )
    delete_route = respx.delete(f"{BASE_URL}/v1/rows/17").mock(return_value=httpx.Response(204))
    count_route = respx.get(f"{BASE_URL}/v1/count").mock(
        return_value=httpx.Response(200, json={"count": 1})
    )
    list_route = respx.get(
        f"{BASE_URL}/v1/rows",
        params={"limit": "10", "offset": "0"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [wire_row(16, 20_260_728, "psc.1.0", "payload")],
                "count": 1,
                "hasMore": False,
                "nextOffset": 1,
            },
        )
    )
    find_route = respx.get(
        f"{BASE_URL}/v1/find",
        params={"q": "psc.1.", "limit": "10", "offset": "0"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [wire_row(16, 20_260_728, "psc.1.0", "payload")],
                "count": 1,
                "hasMore": False,
                "nextOffset": 1,
            },
        )
    )
    range_route = respx.get(
        f"{BASE_URL}/v1/range",
        params={"lo": "20260728", "hi": "20260728", "limit": "10", "offset": "0"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [wire_row(16, 20_260_728, "psc.1.0", "payload")],
                "count": 1,
                "hasMore": False,
                "nextOffset": 1,
            },
        )
    )

    async with client() as asmdb:
        health = await asmdb.health()
        fetched = await asmdb.get(16)
        inserted = await asmdb.insert(Row(id=17, value=-17, tag="psc.1.1", content="next"))
        updated = await asmdb.update(Row(id=17, value=-17, tag="psc.1.1", content="updated"))
        await asmdb.delete(17)
        count = await asmdb.count()
        listed = await asmdb.list(limit=10)
        found = await asmdb.find("psc.1.", limit=10)
        ranged = await asmdb.range(20_260_728, 20_260_728, limit=10)

    assert health.status == "ok"
    assert health.storage_format == "2"
    assert "Authorization" not in health_route.calls.last.request.headers
    assert fetched.id == 16
    assert fetched.value == 20_260_728
    assert fetched.created == EPOCH + timedelta(milliseconds=1_785_001_293_764)
    assert inserted.id == 17
    assert updated.content == "updated"
    assert count == 1
    assert listed.rows == found.rows == ranged.rows
    assert get_route.calls.last.request.headers["Authorization"] == (f"Bearer {TEST_CREDENTIAL}")
    request_payload = cast(
        dict[str, str],
        json.loads(insert_route.calls.last.request.content),
    )
    assert request_payload == {
        "id": "17",
        "value": "-17",
        "tag": "psc.1.1",
        "content": "next",
    }
    assert "created" not in request_payload
    assert cast(
        dict[str, str],
        json.loads(update_route.calls.last.request.content),
    ) == {
        "value": "-17",
        "tag": "psc.1.1",
        "content": "updated",
    }
    assert delete_route.called
    assert count_route.called
    assert list_route.called
    assert find_route.called
    assert range_route.called


@respx.mock
async def test_unauthorized_response_maps_to_typed_error() -> None:
    respx.get(f"{BASE_URL}/v1/count").mock(
        return_value=httpx.Response(
            401,
            json={
                "error": {
                    "code": "unauthorized",
                    "message": "missing or invalid bearer token",
                }
            },
        )
    )

    async with client() as asmdb:
        with pytest.raises(AsmDbUnauthorized) as caught:
            await asmdb.count()

    assert caught.value.code == "unauthorized"
    assert caught.value.status_code == 401


@respx.mock
async def test_missing_row_maps_to_not_found() -> None:
    respx.get(f"{BASE_URL}/v1/rows/999").mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "not_found", "message": "row not found"}},
        )
    )

    async with client() as asmdb:
        with pytest.raises(AsmDbNotFound):
            await asmdb.get(999)


@respx.mock
async def test_server_validation_response_maps_to_validation_error() -> None:
    respx.post(f"{BASE_URL}/v1/rows").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "code": "field_too_long",
                    "message": "content is longer than 175 bytes",
                }
            },
        )
    )

    async with client() as asmdb:
        with pytest.raises(AsmDbValidationError) as caught:
            await asmdb.insert(Row(id=16, value=20_260_728, tag="psc.1.0", content="valid"))

    assert caught.value.code == "field_too_long"


@respx.mock
async def test_rate_limit_honours_retry_after_and_retries() -> None:
    route = respx.get(f"{BASE_URL}/v1/count").mock(
        side_effect=[
            httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"error": {"code": "rate_limited", "message": "slow down"}},
            ),
            httpx.Response(200, json={"count": 7}),
        ]
    )

    async with client() as asmdb:
        assert await asmdb.count() == 7

    assert route.call_count == 2


@respx.mock
async def test_rate_limit_error_retains_retry_after_seconds() -> None:
    route = respx.get(f"{BASE_URL}/v1/count").mock(
        return_value=httpx.Response(
            429,
            headers={"Retry-After": "3"},
            json={"error": {"code": "rate_limited", "message": "slow down"}},
        )
    )

    async with client(retry_attempts=1) as asmdb:
        with pytest.raises(AsmDbRateLimited) as caught:
            await asmdb.count()

    assert caught.value.retry_after == 3
    assert route.call_count == 1


@respx.mock
async def test_upsert_updates_first_then_inserts_on_not_found() -> None:
    update_route = respx.put(f"{BASE_URL}/v1/rows/17").mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "not_found", "message": "row not found"}},
        )
    )
    insert_route = respx.post(f"{BASE_URL}/v1/rows").mock(
        return_value=httpx.Response(
            201,
            json={"row": wire_row(17, -17, "psc.1.1", "new")},
        )
    )

    async with client() as asmdb:
        row = await asmdb.upsert(Row(id=17, value=-17, tag="psc.1.1", content="new"))

    assert row.id == 17
    assert update_route.called and insert_route.called


@pytest.mark.parametrize("status_code", [502, 503, 504])
@respx.mock
async def test_transient_gateway_statuses_are_retried(status_code: int) -> None:
    route = respx.get(f"{BASE_URL}/v1/count").mock(
        side_effect=[
            httpx.Response(status_code, json={"error": {"message": "temporary"}}),
            httpx.Response(200, json={"count": 4}),
        ]
    )

    async with client() as asmdb:
        assert await asmdb.count() == 4

    assert route.call_count == 2


@respx.mock
async def test_cold_start_error_then_health_success() -> None:
    route = respx.get(f"{BASE_URL}/health").mock(
        side_effect=[
            httpx.Response(
                503,
                json={
                    "error": {
                        "code": "instance_starting",
                        "message": "instance is starting",
                    }
                },
            ),
            httpx.Response(
                200,
                json={
                    "engine": "1.7.0",
                    "rows": 0,
                    "status": "ok",
                    "storageFormat": "2",
                },
            ),
        ]
    )

    async with client() as asmdb:
        health = await asmdb.warm(timeout=5)

    assert health.status == "ok"
    assert route.call_count == 2


@respx.mock
async def test_html_cold_start_placeholder_is_retried() -> None:
    route = respx.get(f"{BASE_URL}/health").mock(
        side_effect=[
            httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text="<!doctype html><html><body>Starting...</body></html>",
            ),
            httpx.Response(
                200,
                json={
                    "engine": "1.7.0",
                    "rows": 0,
                    "status": "ok",
                    "storageFormat": "2",
                },
            ),
        ]
    )

    async with client() as asmdb:
        assert (await asmdb.health()).engine == "1.7.0"

    assert route.call_count == 2


@respx.mock
async def test_malformed_json_is_a_non_retryable_protocol_error() -> None:
    route = respx.get(f"{BASE_URL}/v1/count").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            text="{not-json",
        )
    )

    async with client() as asmdb:
        with pytest.raises(AsmDbError, match="malformed JSON"):
            await asmdb.count()

    assert route.call_count == 1


@respx.mock
async def test_successful_post_with_bad_json_is_never_retried() -> None:
    route = respx.post(f"{BASE_URL}/v1/rows").mock(
        return_value=httpx.Response(
            201,
            headers={"Content-Type": "application/json"},
            text="{not-json",
        )
    )

    async with client() as asmdb:
        with pytest.raises(AsmDbError, match="malformed JSON"):
            await asmdb.insert(Row(id=16, value=20_260_728, tag="psc.1.0", content="x"))

    assert route.call_count == 1


@respx.mock
async def test_oversized_content_is_rejected_before_network() -> None:
    route = respx.post(f"{BASE_URL}/v1/rows").mock(return_value=httpx.Response(500))
    invalid = Row.model_construct(
        id=16,
        value=20_260_728,
        tag="psc.1.0",
        content="é" * 88,
        created=None,
        updated=None,
    )

    async with client() as asmdb:
        with pytest.raises(AsmDbValidationError):
            await asmdb.insert(invalid)

    assert not route.called
    with pytest.raises(ValidationError):
        Row(id=16, value=20_260_728, tag="psc.1.0", content="é" * 88)


@respx.mock
async def test_tag_with_space_is_rejected_before_network() -> None:
    route = respx.post(f"{BASE_URL}/v1/rows").mock(return_value=httpx.Response(500))
    invalid = Row.model_construct(
        id=16,
        value=20_260_728,
        tag="psc 1.0",
        content="x",
        created=None,
        updated=None,
    )

    async with client() as asmdb:
        with pytest.raises(AsmDbValidationError):
            await asmdb.insert(invalid)

    assert not route.called
    with pytest.raises(ValidationError):
        Row(id=16, value=20_260_728, tag="psc 1.0", content="x")


@respx.mock
async def test_iter_all_uses_next_offset_across_three_pages() -> None:
    first = respx.get(
        f"{BASE_URL}/v1/rows",
        params={"limit": "2", "offset": "0"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    wire_row(16, 20_260_728, "psc.1.0", "a"),
                    wire_row(17, -17, "psc.1.1", "b"),
                ],
                "count": 2,
                "hasMore": True,
                "nextOffset": 7,
            },
        )
    )
    second = respx.get(
        f"{BASE_URL}/v1/rows",
        params={"limit": "2", "offset": "7"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    wire_row(32, 20_260_729, "psc.2.0", "c"),
                    wire_row(33, -33, "psc.2.1", "d"),
                ],
                "count": 2,
                "hasMore": True,
                "nextOffset": 42,
            },
        )
    )
    third = respx.get(
        f"{BASE_URL}/v1/rows",
        params={"limit": "2", "offset": "42"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [wire_row(48, 20_260_730, "psc.3.0", "e")],
                "count": 1,
                "hasMore": False,
                "nextOffset": 43,
            },
        )
    )

    async with client() as asmdb:
        rows = [row async for row in asmdb.iter_all(page_size=2)]

    assert [row.id for row in rows] == [16, 17, 32, 33, 48]
    assert first.called and second.called and third.called
