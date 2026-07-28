"""Card-level invariants and compensating-write tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.asmdb import AsmDbClient, AsmDbError, AsmDbRepository, Row

BASE_URL = "https://asmdb.example/db/unit-instance"
TEST_CREDENTIAL = "unit-test-credential"
Z85_ALPHABET = (
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#"
)


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


def client() -> AsmDbClient:
    """Avoid test sleeps while retaining production retry mechanics."""
    return AsmDbClient(
        BASE_URL,
        TEST_CREDENTIAL,
        retry_min_wait=0,
        retry_max_wait=0,
    )


def z85_encode(data: bytes) -> str:
    """Create valid part-zero content without importing the codec workstream."""
    padding = (-len(data)) % 4
    padded = data + b"\x00" * padding
    output: list[str] = []
    for start in range(0, len(padded), 4):
        value = int.from_bytes(padded[start : start + 4], "big")
        digits = [""] * 5
        for index in range(4, -1, -1):
            value, digit = divmod(value, 85)
            digits[index] = Z85_ALPHABET[digit]
        output.extend(digits)
    return "".join(output)


def header_content(serial: int, total_len: int) -> str:
    """Encode only the fixed header fields the repository must inspect."""
    header = bytearray(32)
    header[0] = 0x50
    header[1] = 0x01
    header[2:4] = serial.to_bytes(2, "little")
    header[4:6] = total_len.to_bytes(2, "little")
    return z85_encode(bytes(header))


@respx.mock
async def test_write_card_rows_reads_back_every_row() -> None:
    rows = [
        Row(id=16, value=20_260_728, tag="psc.1.0", content="header"),
        Row(id=17, value=-17, tag="psc.1.1", content="continuation"),
    ]
    for row in rows:
        respx.get(f"{BASE_URL}/v1/rows/{row.id}").mock(
            side_effect=[
                httpx.Response(
                    404,
                    json={"error": {"code": "not_found", "message": "row not found"}},
                ),
                httpx.Response(
                    200,
                    json={"row": wire_row(row.id, row.value, row.tag, row.content)},
                ),
            ]
        )
    respx.post(f"{BASE_URL}/v1/rows").mock(
        side_effect=[
            httpx.Response(
                201,
                json={"row": wire_row(row.id, row.value, row.tag, row.content)},
            )
            for row in rows
        ]
    )

    async with client() as asmdb:
        repository = AsmDbRepository(asmdb)
        verified = await repository.write_card_rows(rows)

    assert [row.id for row in verified] == [16, 17]


@respx.mock
async def test_write_mismatch_deletes_every_attempted_row() -> None:
    row = Row(id=16, value=20_260_728, tag="psc.1.0", content="expected")
    respx.get(f"{BASE_URL}/v1/rows/16").mock(
        side_effect=[
            httpx.Response(
                404,
                json={"error": {"code": "not_found", "message": "row not found"}},
            ),
            httpx.Response(
                200,
                json={"row": wire_row(16, 20_260_728, "psc.1.0", "wrong")},
            ),
        ]
    )
    respx.post(f"{BASE_URL}/v1/rows").mock(
        return_value=httpx.Response(
            201,
            json={"row": wire_row(16, 20_260_728, "psc.1.0", "expected")},
        )
    )
    delete_route = respx.delete(f"{BASE_URL}/v1/rows/16").mock(return_value=httpx.Response(204))

    async with client() as asmdb:
        repository = AsmDbRepository(asmdb)
        with pytest.raises(AsmDbError, match="read-back verification"):
            await repository.write_card_rows([row])

    assert delete_route.called


@respx.mock
async def test_read_card_rows_decodes_total_length_and_fetches_direct_ids() -> None:
    respx.get(f"{BASE_URL}/v1/rows/16").mock(
        return_value=httpx.Response(
            200,
            json={
                "row": wire_row(
                    16,
                    20_260_728,
                    "psc.1.0",
                    header_content(1, 281),
                )
            },
        )
    )
    second = respx.get(f"{BASE_URL}/v1/rows/17").mock(
        return_value=httpx.Response(
            200,
            json={"row": wire_row(17, -17, "psc.1.1", "part-one")},
        )
    )
    third = respx.get(f"{BASE_URL}/v1/rows/18").mock(
        return_value=httpx.Response(
            200,
            json={"row": wire_row(18, -18, "psc.1.2", "part-two")},
        )
    )

    async with client() as asmdb:
        rows = await AsmDbRepository(asmdb).read_card_rows(1)

    assert [row.id for row in rows] == [16, 17, 18]
    assert second.called and third.called


@respx.mock
async def test_find_card_by_date_accepts_only_header_rows() -> None:
    route = respx.get(
        f"{BASE_URL}/v1/range",
        params={
            "lo": "20260728",
            "hi": "20260728",
            "limit": "1000",
            "offset": "0",
        },
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [wire_row(16, 20_260_728, "psc.1.0", "header")],
                "count": 1,
                "hasMore": False,
                "nextOffset": 1,
            },
        )
    )

    async with client() as asmdb:
        row = await AsmDbRepository(asmdb).find_card_by_date(20_260_728)

    assert row.id == 16
    assert route.called


@respx.mock
async def test_list_card_serials_pages_with_server_cursors() -> None:
    first = respx.get(
        f"{BASE_URL}/v1/range",
        params={
            "lo": "1",
            "hi": str((1 << 63) - 1),
            "limit": "1000",
            "offset": "0",
        },
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    wire_row(16, 20_260_728, "psc.1.0", "a"),
                    wire_row(32, 20_260_729, "psc.2.0", "b"),
                ],
                "count": 2,
                "hasMore": True,
                "nextOffset": 17,
            },
        )
    )
    second = respx.get(
        f"{BASE_URL}/v1/range",
        params={
            "lo": "1",
            "hi": str((1 << 63) - 1),
            "limit": "1000",
            "offset": "17",
        },
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [wire_row(48, 20_260_730, "psc.3.0", "c")],
                "count": 1,
                "hasMore": False,
                "nextOffset": 18,
            },
        )
    )

    async with client() as asmdb:
        serials = await AsmDbRepository(asmdb).list_card_serials()

    assert serials == [1, 2, 3]
    assert first.called and second.called
