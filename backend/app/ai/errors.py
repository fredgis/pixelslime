"""Exception hierarchy for the AI card-generation pipeline (W4).

Why a dedicated hierarchy: the daily job must be able to tell *where* a card
failed so a bad day can be reconstructed from logs and, where the plan allows,
retried at a single step rather than from scratch. Every failure is raised
loudly with context — nothing in this package silently truncates, defaults or
swallows an error (see ``docs/AGENTS.md`` → "Definition of done").
"""

from __future__ import annotations


class GenerationError(Exception):
    """Base class for every failure in the card-generation pipeline.

    Catch this to treat *any* pipeline problem uniformly (e.g. to raise the
    App Insights alert described in ``docs/PLAN.md`` §5); catch a subclass to
    react to one specific step.
    """


class RollError(GenerationError):
    """The in-code roll could not produce a valid, reproducible draw.

    Raised when the design tokens are inconsistent (e.g. rarity weights that do
    not sum to 1) rather than for anything the model does — the roll never
    involves the model.
    """


class EncodingError(GenerationError):
    """The validated card cannot be packed into a PSC-1 stream.

    Raised by the pre-image gate (``docs/PLAN.md`` §5, "validate the encode before
    spending on the image") when a *trial* :func:`app.codec.encode` fails — either a
    UTF-8 byte-limit overflow (``docs/CODEC.md`` §3.6, stricter than the schema's
    character limits) or the 560-byte stream ceiling — so a card that could never
    be stored fails *before* a ~100-second image generation is spent on it.

    W2 proved this cannot fire for a schema-valid card today (the largest legal
    body, 520 bytes, deflates to a 557-byte stream against the 560-byte ceiling).
    The gate is therefore defence in depth against a future length-limit relaxation
    silently breaking that invariant, not a check against today's code.
    """


class MetadataError(GenerationError):
    """The text model failed to produce usable card metadata."""


class MetadataValidationError(MetadataError):
    """Model output violated a hard constraint after all retries were spent.

    This covers over-length text (``docs/CODEC.md`` §3.6), out-of-range numbers,
    forbidden control characters and duplicate names. It is raised *instead of*
    truncating: a card that does not fit the codec must never be silently
    shortened, because the shortened text would then disagree with the printed
    image.
    """

    def __init__(self, message: str, *, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems: list[str] = problems or []


class ImageGenerationError(GenerationError):
    """The image endpoint (`/images/edits`) failed after retries/backoff."""


class RateLimitError(ImageGenerationError):
    """`/images/edits` kept returning HTTP 429 until the retries were exhausted.

    A subclass of :class:`ImageGenerationError` so existing ``except
    ImageGenerationError`` handlers still catch it, but it additionally carries the
    parsed ``Retry-After`` seconds (``None`` when the server sent no usable header)
    and the number of attempts consumed. W8's daily job can then schedule its own
    backoff from *structured* data (``retry_after``/``attempts``) instead of
    string-matching the message text, which is brittle. The message still contains
    the ``HTTP 429`` marker so a caller that has not yet migrated off substring
    matching keeps working.
    """

    def __init__(
        self, message: str, *, retry_after: float | None = None, attempts: int = 0
    ) -> None:
        super().__init__(message)
        self.retry_after: float | None = retry_after
        self.attempts: int = attempts


class VerificationError(GenerationError):
    """The rendered card failed a step-4 check.

    Attributes let the orchestrator decide whether to retry the image once
    (a soft mismatch) or alert immediately (a technical impossibility such as a
    missing alpha channel).
    """

    def __init__(self, message: str, *, reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.reasons: list[str] = reasons or []


class PostProcessError(GenerationError):
    """Post-processing (alpha trim, thumbnail, hash, palette) failed."""
