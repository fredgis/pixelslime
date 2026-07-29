"""Shared helpers for the two Structured Outputs calls (metadata + verify).

Both the copywriter (``metadata.py``) and the vision check (``verify.py``) talk to
``/chat/completions`` with a strict JSON Schema. The transport, refusal handling
and content extraction are identical, so they live here once; the caller passes
the exception type it wants raised on failure so error typing stays per-step.
"""

from __future__ import annotations

from typing import Any

import httpx


def json_schema_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Build the ``response_format`` block for strict Structured Outputs."""
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema},
    }


async def request_structured(
    client: httpx.AsyncClient,
    body: dict[str, Any],
    *,
    error_cls: type[Exception],
) -> str:
    """POST a chat request and return the assistant's JSON string content.

    Raises ``error_cls`` (loudly, per ``docs/AGENTS.md``) on any transport error,
    non-200 status, model refusal, or empty content — never returns ``None`` to
    signal failure.
    """
    try:
        resp = await client.post("chat/completions", json=body)
    except httpx.HTTPError as exc:
        raise error_cls(f"chat/completions request failed: {exc}") from exc

    if resp.status_code != 200:
        raise error_cls(f"chat/completions returned HTTP {resp.status_code}: {resp.text[:500]}")

    data: Any = resp.json()
    try:
        choice = data["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise error_cls(f"unexpected chat/completions response shape: {exc}") from exc

    refusal = message.get("refusal")
    if refusal:
        raise error_cls(f"model refused the request: {refusal}")

    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise error_cls(
            f"model returned empty content (finish_reason={choice.get('finish_reason')!r})"
        )
    return content
