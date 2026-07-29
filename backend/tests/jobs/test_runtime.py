"""Production-only adapters keep request pacing and CLI selection testable."""

from __future__ import annotations

import httpx
from _jobs_helpers import FakeClock

from app.jobs.runtime import ImageRateLimitedClient, ImageRequestGate
from app.jobs.telemetry import AppInsightsMetricSink


async def test_image_request_gate_never_starts_more_than_two_per_minute() -> None:
    clock = FakeClock()
    gate = ImageRequestGate(clock=clock.monotonic, sleep=clock.sleep)

    await gate.acquire()
    await gate.acquire()
    await gate.acquire()

    assert clock.sleeps == [60.0]


async def test_app_insights_sink_posts_metric_batch_to_connection_endpoint() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        sink = AppInsightsMetricSink(
            "InstrumentationKey=00000000-0000-0000-0000-000000000001;"
            "IngestionEndpoint=https://westeurope-1.in.applicationinsights.azure.com/",
            client=client,
        )
        sink.record(
            "pixelslime.job.step.duration_ms",
            12.5,
            {"job": "daily", "step": "generation", "serial": 7},
        )
        await sink.flush()

    assert len(requests) == 1
    assert str(requests[0].url) == (
        "https://westeurope-1.in.applicationinsights.azure.com/v2/track"
    )
    payload = requests[0].read().decode()
    assert "pixelslime.job.step.duration_ms" in payload
    assert '"serial":"7"' in payload


async def test_ai_client_gate_applies_to_relative_image_urls_only() -> None:
    clock = FakeClock()
    gate = ImageRequestGate(clock=clock.monotonic, sleep=clock.sleep)

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    async with httpx.AsyncClient(
        base_url="https://ai.example/openai/v1/",
        transport=httpx.MockTransport(respond),
    ) as client:
        gated = ImageRateLimitedClient(client, gate)
        await gated.post("images/edits")
        await gated.post("chat/completions")
        await gated.post("images/edits")
        await gated.post("images/edits")

    assert clock.sleeps == [60.0]
