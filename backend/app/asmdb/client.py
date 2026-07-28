"""Async HTTP client for the hosted asmDB row API."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import cast

import httpx
from pydantic import ValidationError
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
)
from tenacity.stop import stop_base
from tenacity.wait import wait_random_exponential

from .errors import (
    AsmDbError,
    AsmDbNotFound,
    AsmDbRateLimited,
    AsmDbStarting,
    AsmDbUnauthorized,
    AsmDbValidationError,
)
from .models import Health, Row, RowPage

_DECIMAL_RE = re.compile(r"-?[0-9]+\Z")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})


class _AsmDbTransientError(AsmDbError):
    """Mark a response or transport failure as safe for tenacity to retry."""


class AsmDbClient:
    """Keep asmDB's bearer credential and string-integer protocol server-side."""

    def __init__(
        self,
        base_url: str | httpx.URL,
        token: str | None = None,
        *,
        timeout: float | httpx.Timeout = 30.0,
        warm_timeout: float = 120.0,
        retry_attempts: int = 5,
        retry_min_wait: float = 0.25,
        retry_max_wait: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed_url = httpx.URL(base_url)
        if parsed_url.scheme not in {"http", "https"} or parsed_url.host is None:
            raise AsmDbValidationError("base_url must be an absolute HTTP(S) URL")
        if warm_timeout <= 0:
            raise AsmDbValidationError("warm_timeout must be positive")
        if retry_attempts < 1:
            raise AsmDbValidationError("retry_attempts must be at least 1")
        if retry_min_wait < 0 or retry_max_wait < retry_min_wait:
            raise AsmDbValidationError("retry wait bounds are invalid")

        self._base_url = str(parsed_url).rstrip("/")
        self._token = token if token else None
        self._timeout = timeout
        self._warm_timeout = warm_timeout
        self._retry_attempts = retry_attempts
        self._exponential_wait = wait_random_exponential(
            multiplier=retry_min_wait,
            max=retry_max_wait,
        )
        self._client = http_client or httpx.AsyncClient(follow_redirects=True)
        self._owns_client = http_client is None

    async def __aenter__(self) -> AsmDbClient:
        """Make ownership explicit when the client creates its HTTP transport."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release only transports created by this wrapper."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned connection pool without surprising injected clients."""
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> Health:
        """Probe readiness without ever attaching the instance bearer credential."""
        try:
            async for attempt in self._retryer(stop_after_attempt(self._retry_attempts)):
                with attempt:
                    return await self._health_once()
        except _AsmDbTransientError as exc:
            raise self._public_transient_error(exc) from exc
        raise AsmDbError("asmDB health retry loop ended unexpectedly")

    async def warm(self, *, timeout: float | None = None) -> Health:  # noqa: ASYNC109
        """Poll through scale-to-zero activation before a write workflow begins."""
        deadline = self._warm_timeout if timeout is None else timeout
        if deadline <= 0:
            raise AsmDbValidationError("warm timeout must be positive")
        try:
            async for attempt in self._retryer(stop_after_delay(deadline)):
                with attempt:
                    return await self._health_once()
        except _AsmDbTransientError as exc:
            raise self._public_transient_error(exc) from exc
        raise AsmDbError("asmDB warm-up retry loop ended unexpectedly")

    async def get(self, row_id: int) -> Row:
        """Read one deterministic row id without scanning the slot region."""
        normalized_id = self._validate_id(row_id)
        response = await self._request("GET", f"/v1/rows/{normalized_id}")
        self._require_status(response, 200)
        return self._parse_row_envelope(response)

    async def insert(self, row: Row) -> Row:
        """Create a row while keeping timestamps owned by the engine."""
        validated = self._validate_row(row)
        response = await self._request(
            "POST",
            "/v1/rows",
            json_body=self._row_create_payload(validated),
            retry_transport=False,
        )
        self._require_status(response, 201)
        return self._parse_row_envelope(response)

    async def update(self, row: Row) -> Row:
        """Replace mutable columns while preserving engine-owned timestamps."""
        validated = self._validate_row(row)
        response = await self._request(
            "PUT",
            f"/v1/rows/{validated.id}",
            json_body=self._row_patch_payload(validated),
        )
        self._require_status(response, 200)
        return self._parse_row_envelope(response)

    async def upsert(self, row: Row) -> Row:
        """Prefer idempotent PUT and create only after an explicit not-found."""
        validated = self._validate_row(row)
        try:
            return await self.update(validated)
        except AsmDbNotFound:
            try:
                return await self.insert(validated)
            except AsmDbError as exc:
                if exc.code != "already_exists":
                    raise
                return await self.update(validated)

    async def delete(self, row_id: int) -> None:
        """Remove a deterministic row so failed multi-row writes can compensate."""
        normalized_id = self._validate_id(row_id)
        response = await self._request("DELETE", f"/v1/rows/{normalized_id}")
        self._require_status(response, 204)

    async def count(self) -> int:
        """Return the live-row count as a Python integer."""
        response = await self._request("GET", "/v1/count")
        self._require_status(response, 200)
        data = self._decode_object(response)
        return self._json_int(data.get("count"), "count")

    async def list(self, limit: int = 100, offset: int = 0) -> RowPage:
        """Retain the service cursor because slot scans can skip tombstones."""
        page_limit, page_offset = self._validate_page(limit, offset)
        response = await self._request(
            "GET",
            "/v1/rows",
            params={"limit": str(page_limit), "offset": str(page_offset)},
        )
        self._require_status(response, 200)
        return self._parse_page(response)

    async def iter_all(self, *, page_size: int = 1000) -> AsyncIterator[Row]:
        """Follow each server-provided cursor so sparse pages cannot lose rows."""
        page_limit, offset = self._validate_page(page_size, 0)
        while True:
            page = await self.list(limit=page_limit, offset=offset)
            for row in page.rows:
                yield row
            if not page.has_more:
                return
            if page.next_offset <= offset:
                raise AsmDbError(
                    "asmDB returned a non-advancing pagination cursor",
                    code="invalid_pagination",
                )
            offset = page.next_offset

    async def find(self, q: str, limit: int = 100, offset: int = 0) -> RowPage:
        """Run a bounded substring full scan; never use this on a hot path."""
        if not q or any(character in q for character in "\r\n\x00"):
            raise AsmDbValidationError("q must be a non-empty single-line string")
        page_limit, page_offset = self._validate_page(limit, offset)
        response = await self._request(
            "GET",
            "/v1/find",
            params={"q": q, "limit": str(page_limit), "offset": str(page_offset)},
        )
        self._require_status(response, 200)
        return self._parse_page(response)

    async def range(
        self,
        lo: int,
        hi: int,
        limit: int = 100,
        offset: int = 0,
    ) -> RowPage:
        """Run a bounded value full scan; never use this on a hot path."""
        lower = self._validate_value(lo)
        upper = self._validate_value(hi)
        page_limit, page_offset = self._validate_page(limit, offset)
        response = await self._request(
            "GET",
            "/v1/range",
            params={
                "lo": str(lower),
                "hi": str(upper),
                "limit": str(page_limit),
                "offset": str(page_offset),
            },
        )
        self._require_status(response, 200)
        return self._parse_page(response)

    async def _health_once(self) -> Health:
        response = await self._send_once(
            "GET",
            "/health",
            authenticated=False,
            retry_transport=True,
        )
        self._require_status(response, 200)
        data = self._decode_object(response)
        health = self._build_health(data)
        if health.status != "ok":
            raise AsmDbStarting(
                f"asmDB health status is {health.status!r}",
                code="instance_starting",
                status_code=response.status_code,
            )
        return health

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, str] | None = None,
        retry_transport: bool = True,
    ) -> httpx.Response:
        try:
            async for attempt in self._retryer(stop_after_attempt(self._retry_attempts)):
                with attempt:
                    return await self._send_once(
                        method,
                        path,
                        params=params,
                        json_body=json_body,
                        authenticated=True,
                        retry_transport=retry_transport,
                    )
        except _AsmDbTransientError as exc:
            raise self._public_transient_error(exc) from exc
        raise AsmDbError("asmDB request retry loop ended unexpectedly")

    async def _send_once(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, str] | None = None,
        authenticated: bool,
        retry_transport: bool,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if authenticated and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            response = await self._client.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json_body,
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.TransportError as exc:
            error_type = _AsmDbTransientError if retry_transport else AsmDbError
            raise error_type("asmDB request failed before a response was received") from exc
        self._raise_for_response(response)
        return response

    def _retryer(
        self,
        stop: stop_base,
    ) -> AsyncRetrying:
        return AsyncRetrying(
            retry=retry_if_exception_type((AsmDbStarting, AsmDbRateLimited, _AsmDbTransientError)),
            wait=self._wait_for_retry,
            stop=stop,
            reraise=True,
        )

    def _wait_for_retry(self, retry_state: RetryCallState) -> float:
        exponential = float(self._exponential_wait(retry_state))
        if retry_state.outcome is None:
            return exponential
        exception = retry_state.outcome.exception()
        if isinstance(exception, AsmDbError) and exception.retry_after is not None:
            return max(exponential, exception.retry_after)
        return exponential

    @staticmethod
    def _public_transient_error(exc: _AsmDbTransientError) -> AsmDbError:
        return AsmDbError(
            exc.message,
            code=exc.code,
            status_code=exc.status_code,
            detail=exc.detail,
            retry_after=exc.retry_after,
        )

    def _raise_for_response(self, response: httpx.Response) -> None:
        if self._looks_like_html(response):
            raise AsmDbStarting(
                "asmDB returned an HTML cold-start placeholder",
                code="instance_starting",
                status_code=response.status_code,
            )

        code, message, detail = self._error_fields(response)
        retry_after = self._retry_after(response.headers.get("Retry-After"))
        if code == "instance_starting":
            raise AsmDbStarting(
                message or "asmDB instance is starting",
                code=code,
                status_code=response.status_code,
                detail=detail,
                retry_after=retry_after,
            )
        if response.status_code == 429:
            raise AsmDbRateLimited(
                message or "asmDB rate limit exceeded",
                code=code or "rate_limited",
                status_code=response.status_code,
                detail=detail,
                retry_after=retry_after,
            )
        if response.status_code in _RETRYABLE_STATUS_CODES:
            raise _AsmDbTransientError(
                message or f"asmDB temporarily unavailable ({response.status_code})",
                code=code,
                status_code=response.status_code,
                detail=detail,
                retry_after=retry_after,
            )
        if response.status_code >= 400 or code is not None:
            self._raise_mapped_error(response.status_code, code, message, detail)

    @staticmethod
    def _raise_mapped_error(
        status_code: int,
        code: str | None,
        message: str | None,
        detail: str | None,
    ) -> None:
        text = message or f"asmDB request failed with HTTP {status_code}"
        if status_code in {401, 403} or code == "unauthorized":
            raise AsmDbUnauthorized(
                text,
                code=code,
                status_code=status_code,
                detail=detail,
            )
        if status_code == 404 or code == "not_found":
            raise AsmDbNotFound(
                text,
                code=code,
                status_code=status_code,
                detail=detail,
            )
        if status_code in {400, 422} or code in {
            "field_too_long",
            "invalid_request",
            "request_too_large",
        }:
            raise AsmDbValidationError(
                text,
                code=code,
                status_code=status_code,
                detail=detail,
            )
        raise AsmDbError(
            text,
            code=code,
            status_code=status_code,
            detail=detail,
        )

    @staticmethod
    def _looks_like_html(response: httpx.Response) -> bool:
        content_type = response.headers.get("Content-Type", "").lower()
        prefix = response.content.lstrip()[:32].lower()
        return "text/html" in content_type or prefix.startswith((b"<!doctype html", b"<html"))

    @staticmethod
    def _error_fields(
        response: httpx.Response,
    ) -> tuple[str | None, str | None, str | None]:
        try:
            payload = cast(object, response.json())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, None, None
        if not isinstance(payload, dict):
            return None, None, None
        error = payload.get("error")
        if not isinstance(error, dict):
            return None, None, None
        code = error.get("code")
        message = error.get("message")
        detail = error.get("detail")
        return (
            code if isinstance(code, str) else None,
            message if isinstance(message, str) else None,
            detail if isinstance(detail, str) else None,
        )

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return max(0.0, (parsed.astimezone(UTC) - datetime.now(UTC)).total_seconds())

    @staticmethod
    def _require_status(response: httpx.Response, expected: int) -> None:
        if response.status_code != expected:
            raise AsmDbError(
                f"asmDB returned HTTP {response.status_code}; expected {expected}",
                status_code=response.status_code,
            )

    @staticmethod
    def _decode_object(response: httpx.Response) -> dict[str, object]:
        try:
            payload = cast(object, response.json())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AsmDbError(
                "asmDB returned malformed JSON",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise AsmDbError(
                "asmDB returned a non-object JSON response",
                status_code=response.status_code,
            )
        return cast(dict[str, object], payload)

    def _parse_row_envelope(self, response: httpx.Response) -> Row:
        data = self._decode_object(response)
        raw_row = data.get("row")
        if not isinstance(raw_row, dict):
            raise AsmDbError(
                "asmDB response is missing a row object",
                status_code=response.status_code,
            )
        return self._row_from_wire(cast(dict[str, object], raw_row))

    def _parse_page(self, response: httpx.Response) -> RowPage:
        data = self._decode_object(response)
        raw_rows = data.get("rows")
        if not isinstance(raw_rows, list):
            raise AsmDbError(
                "asmDB page is missing its rows array",
                status_code=response.status_code,
            )
        rows: list[Row] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                raise AsmDbError(
                    "asmDB page contains a non-object row",
                    status_code=response.status_code,
                )
            rows.append(self._row_from_wire(cast(dict[str, object], raw_row)))
        try:
            return RowPage(
                rows=tuple(rows),
                count=self._json_int(data.get("count"), "count"),
                has_more=self._json_bool(data.get("hasMore"), "hasMore"),
                next_offset=self._json_int(data.get("nextOffset"), "nextOffset"),
            )
        except ValidationError as exc:
            raise AsmDbError(
                "asmDB returned invalid pagination metadata",
                status_code=response.status_code,
                detail=str(exc),
            ) from exc

    def _row_from_wire(self, data: Mapping[str, object]) -> Row:
        try:
            row_id = self._decimal_string(data.get("id"), "row.id")
            value = self._decimal_string(data.get("value"), "row.value")
            created = self._wire_timestamp(data.get("created"), "row.created")
            updated = self._wire_timestamp(data.get("updated"), "row.updated")
            tag = self._json_string(data.get("tag"), "row.tag")
            content = self._json_string(data.get("content"), "row.content")
            return Row(
                id=row_id,
                value=value,
                tag=tag,
                content=content,
                created=created,
                updated=updated,
            )
        except (AsmDbValidationError, ValidationError) as exc:
            if isinstance(exc, AsmDbValidationError):
                raise
            raise AsmDbValidationError(
                "asmDB returned a row that violates the row contract",
                detail=str(exc),
            ) from exc

    @staticmethod
    def _build_health(data: Mapping[str, object]) -> Health:
        try:
            return Health(
                engine=AsmDbClient._json_string(data.get("engine"), "engine"),
                rows=AsmDbClient._json_int(data.get("rows"), "rows"),
                status=AsmDbClient._json_string(data.get("status"), "status"),
                storage_format=AsmDbClient._json_string(
                    data.get("storageFormat"),
                    "storageFormat",
                ),
            )
        except ValidationError as exc:
            raise AsmDbError(
                "asmDB returned an invalid health response",
                detail=str(exc),
            ) from exc

    @staticmethod
    def _row_create_payload(row: Row) -> dict[str, str]:
        return {
            "id": str(row.id),
            "value": str(row.value),
            "tag": row.tag,
            "content": row.content,
        }

    @staticmethod
    def _row_patch_payload(row: Row) -> dict[str, str]:
        return {
            "value": str(row.value),
            "tag": row.tag,
            "content": row.content,
        }

    @staticmethod
    def _validate_row(row: Row) -> Row:
        if not isinstance(row, Row):
            raise AsmDbValidationError("row must be an asmdb.models.Row")
        try:
            return Row.model_validate(row.model_dump(), strict=True)
        except ValidationError as exc:
            raise AsmDbValidationError(
                "row violates the asmDB row contract",
                detail=str(exc),
            ) from exc

    @staticmethod
    def _validate_id(row_id: int) -> int:
        if isinstance(row_id, bool) or not isinstance(row_id, int):
            raise AsmDbValidationError("id must be an integer")
        if not 1 <= row_id <= (1 << 64) - 1:
            raise AsmDbValidationError("id must be a u64 integer >= 1")
        return row_id

    @staticmethod
    def _validate_value(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AsmDbValidationError("value must be an integer")
        if not -(1 << 63) <= value <= (1 << 63) - 1:
            raise AsmDbValidationError("value must fit in an i64")
        return value

    @staticmethod
    def _validate_page(limit: int, offset: int) -> tuple[int, int]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise AsmDbValidationError("limit must be an integer from 1 through 1000")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise AsmDbValidationError("offset must be a non-negative integer")
        return limit, offset

    @staticmethod
    def _decimal_string(value: object, field_name: str) -> int:
        if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
            raise AsmDbValidationError(f"{field_name} must be a decimal JSON string")
        return int(value)

    @staticmethod
    def _json_int(value: object, field_name: str) -> int:
        if isinstance(value, bool):
            raise AsmDbError(f"{field_name} must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and _DECIMAL_RE.fullmatch(value) is not None:
            return int(value)
        raise AsmDbError(f"{field_name} must be an integer")

    @staticmethod
    def _json_bool(value: object, field_name: str) -> bool:
        if not isinstance(value, bool):
            raise AsmDbError(f"{field_name} must be a boolean")
        return value

    @staticmethod
    def _json_string(value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise AsmDbError(f"{field_name} must be a string")
        return value

    @staticmethod
    def _wire_timestamp(value: object, field_name: str) -> datetime | None:
        if value is None:
            return None
        milliseconds = AsmDbClient._decimal_string(value, field_name)
        if milliseconds < 0:
            raise AsmDbValidationError(f"{field_name} must be a u64 decimal string")
        try:
            return _EPOCH + timedelta(milliseconds=milliseconds)
        except OverflowError as exc:
            raise AsmDbValidationError(f"{field_name} is outside Python's datetime range") from exc
