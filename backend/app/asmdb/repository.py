"""Card-oriented row operations that do not depend on the PSC-1 codec package."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from datetime import date

from .client import AsmDbClient
from .errors import AsmDbError, AsmDbNotFound, AsmDbValidationError
from .models import MAX_I64, Row

_Z85_ALPHABET = (
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#"
)
_Z85_DIGITS = {character: index for index, character in enumerate(_Z85_ALPHABET)}
_CARD_CHUNK_BYTES = 140
_CARD_HEADER_BYTES = 32
_MAX_CARD_PARTS = 4
_MAX_SERIAL = 65535


class AsmDbRepository:
    """Enforce PSC-1 row invariants around the lower-level REST client."""

    def __init__(self, client: AsmDbClient) -> None:
        self._client = client

    async def write_card_rows(self, rows: Iterable[Row]) -> list[Row]:
        """Compensate any failed or unverifiable write so partial cards do not remain."""
        expected = tuple(rows)
        serial = self._validate_card_rows(expected)

        for row in expected:
            try:
                await self._client.get(row.id)
            except AsmDbNotFound:
                continue
            raise AsmDbError(
                f"card {serial} row {row.id} already exists",
                code="already_exists",
            )

        attempted_ids: list[int] = []
        try:
            for row in expected:
                attempted_ids.append(row.id)
                await self._client.insert(row)

            verified: list[Row] = []
            for expected_row in expected:
                actual = await self._client.get(expected_row.id)
                if not self._same_payload(actual, expected_row):
                    raise AsmDbError(
                        f"card {serial} row {expected_row.id} failed read-back verification",
                        code="verification_failed",
                    )
                verified.append(actual)
        except AsmDbError as exc:
            cleanup_errors = await self._delete_rows(attempted_ids)
            if cleanup_errors:
                raise AsmDbError(
                    f"card {serial} write failed and cleanup was incomplete",
                    code="rollback_failed",
                    detail="; ".join(cleanup_errors),
                ) from exc
            raise
        return verified

    async def read_card_rows(self, serial: int) -> list[Row]:
        """Read part zero first so the remaining deterministic ids require no scan."""
        normalized_serial = self._validate_serial(serial)
        header_row = await self._client.get(normalized_serial * 16)
        self._validate_stored_part(header_row, normalized_serial, 0)
        header = self._decode_header_prefix(header_row.content)

        encoded_serial = int.from_bytes(header[2:4], "little")
        if encoded_serial != normalized_serial:
            raise AsmDbError(
                "card header serial "
                f"{encoded_serial} does not match row serial {normalized_serial}",
                code="invalid_card_rows",
            )
        total_len = int.from_bytes(header[4:6], "little")
        if not _CARD_HEADER_BYTES <= total_len <= _CARD_CHUNK_BYTES * _MAX_CARD_PARTS:
            raise AsmDbError(
                f"card {normalized_serial} has invalid total_len {total_len}",
                code="invalid_card_rows",
            )
        expected_parts = (total_len + _CARD_CHUNK_BYTES - 1) // _CARD_CHUNK_BYTES

        rows = [header_row]
        for part in range(1, expected_parts):
            row = await self._client.get(normalized_serial * 16 + part)
            self._validate_stored_part(row, normalized_serial, part)
            rows.append(row)
        return rows

    async def find_card_by_date(self, yyyymmdd: int) -> Row:
        """Use the date full scan only for deliberate lookup, never a hot path."""
        target = self._validate_date(yyyymmdd)
        matches = [row async for row in self._iter_range(target, target)]
        for row in matches:
            if row.value != target or row.value <= 0 or row.id % 16 != 0:
                raise AsmDbError(
                    "date range returned a non-header card row",
                    code="invalid_card_rows",
                )
            self._validate_stored_part(row, self._validate_serial(row.id // 16), 0)
        if not matches:
            raise AsmDbNotFound(
                f"no card exists for date {target}",
                code="not_found",
                status_code=404,
            )
        if len(matches) != 1:
            raise AsmDbError(
                f"date {target} returned {len(matches)} card headers",
                code="duplicate_card_date",
            )
        return matches[0]

    async def list_card_serials(self) -> list[int]:
        """Accept one deliberate positive-value full scan for offline index rebuilds."""
        serials: set[int] = set()
        async for row in self._iter_range(1, MAX_I64):
            if row.value <= 0 or row.id % 16 != 0:
                raise AsmDbError(
                    "positive value range returned a non-header card row",
                    code="invalid_card_rows",
                )
            serial = self._validate_serial(row.id // 16)
            self._validate_stored_part(row, serial, 0)
            serials.add(serial)
        return sorted(serials)

    async def _iter_range(self, lo: int, hi: int) -> AsyncIterator[Row]:
        offset = 0
        while True:
            page = await self._client.range(lo, hi, limit=1000, offset=offset)
            for row in page.rows:
                yield row
            if not page.has_more:
                return
            if page.next_offset <= offset:
                raise AsmDbError(
                    "asmDB returned a non-advancing range cursor",
                    code="invalid_pagination",
                )
            offset = page.next_offset

    async def _delete_rows(self, row_ids: Iterable[int]) -> list[str]:
        errors: list[str] = []
        for row_id in reversed(tuple(row_ids)):
            try:
                await self._client.delete(row_id)
            except AsmDbNotFound:
                continue
            except AsmDbError as exc:
                errors.append(f"row {row_id}: {exc}")
        return errors

    @staticmethod
    def _validate_card_rows(rows: tuple[Row, ...]) -> int:
        if not rows:
            raise AsmDbValidationError("a card write requires at least one row")
        if len(rows) > _MAX_CARD_PARTS:
            raise AsmDbValidationError("PSC-1 cards may use at most four rows")

        serial = AsmDbRepository._validate_serial(rows[0].id // 16)
        expected_parts = list(range(len(rows)))
        actual_parts = [row.id % 16 for row in rows]
        if actual_parts != expected_parts:
            raise AsmDbValidationError(
                "card rows must be ordered contiguous parts starting at zero"
            )
        if len({row.id for row in rows}) != len(rows):
            raise AsmDbValidationError("card row ids must be unique")

        for part, row in enumerate(rows):
            if row.id != serial * 16 + part:
                raise AsmDbValidationError("all card rows must belong to one serial")
            if row.tag != f"psc.{serial}.{part}":
                raise AsmDbValidationError(f"row {row.id} must use tag psc.{serial}.{part}")
            if part == 0:
                AsmDbRepository._validate_date(row.value)
            if part > 0 and row.value != -row.id:
                raise AsmDbValidationError(f"continuation row {row.id} value must equal {-row.id}")
        return serial

    @staticmethod
    def _validate_stored_part(row: Row, serial: int, part: int) -> None:
        if row.id != serial * 16 + part or row.tag != f"psc.{serial}.{part}":
            raise AsmDbError(
                f"stored row {row.id} violates card addressing for serial {serial} part {part}",
                code="invalid_card_rows",
            )
        if part == 0:
            try:
                AsmDbRepository._validate_date(row.value)
            except AsmDbValidationError as exc:
                raise AsmDbError(
                    "stored card header does not contain a valid YYYYMMDD value",
                    code="invalid_card_rows",
                ) from exc
        if part > 0 and row.value != -row.id:
            raise AsmDbError(f"stored continuation row {row.id} has an invalid value")

    @staticmethod
    def _decode_header_prefix(content: str) -> bytes:
        if len(content) < 10:
            raise AsmDbError("card part zero is too short to contain a PSC-1 header")
        decoded = bytearray()
        for group_start in range(0, 10, 5):
            value = 0
            for character in content[group_start : group_start + 5]:
                digit = _Z85_DIGITS.get(character)
                if digit is None:
                    raise AsmDbError(
                        "card part zero contains a character outside the Z85 alphabet",
                        code="invalid_card_rows",
                    )
                value = value * 85 + digit
            if value > 0xFFFFFFFF:
                raise AsmDbError(
                    "card part zero contains an overflowing Z85 group",
                    code="invalid_card_rows",
                )
            decoded.extend(value.to_bytes(4, "big"))

        prefix = bytes(decoded[:6])
        if prefix[0] != 0x50 or prefix[1] != 0x01:
            raise AsmDbError(
                "card part zero does not contain a PSC-1 header",
                code="invalid_card_rows",
            )
        return prefix

    @staticmethod
    def _same_payload(left: Row, right: Row) -> bool:
        return (
            left.id == right.id
            and left.value == right.value
            and left.tag == right.tag
            and left.content == right.content
        )

    @staticmethod
    def _validate_serial(serial: int) -> int:
        if isinstance(serial, bool) or not isinstance(serial, int):
            raise AsmDbValidationError("serial must be an integer")
        if not 1 <= serial <= _MAX_SERIAL:
            raise AsmDbValidationError("serial must be from 1 through 65535")
        return serial

    @staticmethod
    def _validate_date(yyyymmdd: int) -> int:
        if isinstance(yyyymmdd, bool) or not isinstance(yyyymmdd, int):
            raise AsmDbValidationError("date must be a YYYYMMDD integer")
        year = yyyymmdd // 10000
        month = yyyymmdd // 100 % 100
        day = yyyymmdd % 100
        try:
            date(year, month, day)
        except ValueError as exc:
            raise AsmDbValidationError("date must be a valid YYYYMMDD integer") from exc
        return yyyymmdd


CardRepository = AsmDbRepository
