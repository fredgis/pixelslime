"""Strict Python models for asmDB rows and response metadata."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_U64 = (1 << 64) - 1
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
MAX_TAG_BYTES = 39
MAX_CONTENT_BYTES = 175
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _utf8_length(value: str, field_name: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field_name} must be valid UTF-8") from exc


class Row(BaseModel):
    """Represent row integers safely after the JSON-string wire boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: int = Field(ge=1, le=MAX_U64)
    value: int = Field(ge=MIN_I64, le=MAX_I64)
    tag: str
    content: str
    created: datetime | None = None
    updated: datetime | None = None

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str) -> str:
        """Reject values the sidecar cannot place in its single-token column."""
        if not value:
            raise ValueError("tag must not be empty")
        if _utf8_length(value, "tag") > MAX_TAG_BYTES:
            raise ValueError(f"tag must be at most {MAX_TAG_BYTES} UTF-8 bytes")
        if any(character in value for character in " \t\r\n\x00"):
            raise ValueError("tag must not contain space, tab, CR, LF, or NUL")
        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Reject text that would be truncated or rejected by the sidecar."""
        if _utf8_length(value, "content") > MAX_CONTENT_BYTES:
            raise ValueError(f"content must be at most {MAX_CONTENT_BYTES} UTF-8 bytes")
        if any(character in value for character in "\r\n\x00"):
            raise ValueError("content must not contain CR, LF, or NUL")
        return value

    @field_validator("created", "updated")
    @classmethod
    def validate_timestamp(cls, value: datetime | None) -> datetime | None:
        """Keep engine timestamps unambiguous by requiring timezone awareness."""
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must be timezone-aware")
        if value is not None and value < _EPOCH:
            raise ValueError("timestamps must be non-negative Unix epoch values")
        return value


class RowPage(BaseModel):
    """Retain server pagination cursors so callers never invent offsets."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    rows: tuple[Row, ...]
    count: int = Field(ge=0)
    has_more: bool
    next_offset: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_count(self) -> RowPage:
        """Detect a corrupt page before its cursor can lose or duplicate rows."""
        if self.count != len(self.rows):
            raise ValueError("page count does not match the number of rows")
        return self


class Health(BaseModel):
    """Expose the small unauthenticated readiness response with real integers."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    engine: str = Field(min_length=1)
    rows: int = Field(ge=0)
    status: str
    storage_format: str
