"""PixelSlime AI card-generation pipeline (workstream W4).

Public entry point: :func:`app.ai.pipeline.generate_card`, which runs
roll → metadata → image → verify → post-process and returns a validated card
dict plus the image bytes, with no side effects (no upload, no DB, no chain).
"""

from __future__ import annotations

from .auth import azure_token_provider, build_async_client
from .errors import (
    GenerationError,
    ImageGenerationError,
    MetadataError,
    MetadataValidationError,
    PostProcessError,
    RollError,
    VerificationError,
)
from .models import Card, Flags
from .pipeline import PipelineResult, generate_card
from .prompt import MasterPrompt, load_master_prompt
from .roll import MintedCard, Roll, roll

__all__ = [
    "Card",
    "Flags",
    "GenerationError",
    "ImageGenerationError",
    "MasterPrompt",
    "MetadataError",
    "MetadataValidationError",
    "MintedCard",
    "PipelineResult",
    "PostProcessError",
    "Roll",
    "RollError",
    "VerificationError",
    "azure_token_provider",
    "build_async_client",
    "generate_card",
    "load_master_prompt",
    "roll",
]
