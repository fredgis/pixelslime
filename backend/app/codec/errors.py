"""Exception hierarchy for the PSC-1 codec.

Every failure mode in this package raises a subclass of :class:`CodecError` so a
caller can catch the whole codec with a single ``except CodecError`` while still
being able to discriminate on the specific fault when it matters (a corrupted row
is operationally very different from an over-long field). This exists because
``docs/CODEC.md`` §5 mandates *loud* failure: nothing here is ever silently
truncated, defaulted or swallowed, so every guard needs a concrete exception to
raise.
"""

from __future__ import annotations


class CodecError(Exception):
    """Base class for every PSC-1 encode/decode failure."""


class Z85Error(CodecError):
    """The Z85 text envelope is malformed (bad length, char or overflow)."""


class HeaderError(CodecError):
    """The 32-byte header is malformed, mis-sized, or carries a bad magic/version."""


class CrcError(CodecError):
    """The stored CRC-16 does not match the recomputed one: the stream is corrupt."""


class DictionaryError(CodecError):
    """The pinned DEFLATE dictionary is missing or does not match its version hash."""


class FieldLimitError(CodecError):
    """A text field breaks a length limit or contains a forbidden control byte."""


class StreamTooLargeError(CodecError):
    """The serialised stream exceeds the 4-row (560-byte) ceiling."""


class RowError(CodecError):
    """The asmDB rows are inconsistent: missing, duplicated, mixed serial or bad value."""


class BodyError(CodecError):
    """The compressed body cannot be inflated or does not hold exactly five fields."""
