"""Buffered custom metrics sent directly to Application Insights ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from .models import MetricProperties

_DEFAULT_INGESTION_ENDPOINT = "https://dc.services.visualstudio.com"


def _connection_parts(connection_string: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for component in connection_string.split(";"):
        if not component.strip():
            continue
        key, separator, value = component.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError("invalid Application Insights connection string")
        parts[key.strip().casefold()] = value.strip()
    return parts


class AppInsightsMetricSink:
    """Buffer metric envelopes and submit one compact batch at job shutdown."""

    def __init__(self, connection_string: str, *, client: httpx.AsyncClient) -> None:
        parts = _connection_parts(connection_string)
        try:
            self._instrumentation_key = parts["instrumentationkey"]
        except KeyError as exc:
            raise ValueError(
                "Application Insights connection string lacks InstrumentationKey"
            ) from exc
        endpoint = parts.get("ingestionendpoint", _DEFAULT_INGESTION_ENDPOINT)
        self._track_url = endpoint.rstrip("/") + "/v2/track"
        self._client = client
        self._envelopes: list[dict[str, Any]] = []

    def record(
        self,
        name: str,
        value: float,
        properties: MetricProperties,
    ) -> None:
        """Queue one measurement without adding network latency to a job step."""
        if not name:
            raise ValueError("metric name must not be empty")
        dimensions = {key: str(item) for key, item in properties.items() if item is not None}
        self._envelopes.append(
            {
                "name": (f"Microsoft.ApplicationInsights.{self._instrumentation_key}.Metric"),
                "time": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                "iKey": self._instrumentation_key,
                "data": {
                    "baseType": "MetricData",
                    "baseData": {
                        "ver": 2,
                        "metrics": [
                            {
                                "name": name,
                                "kind": "Measurement",
                                "value": value,
                                "count": 1,
                            }
                        ],
                        "properties": dimensions,
                    },
                },
            }
        )

    async def flush(self) -> None:
        """Send all queued measurements as one ingestion request."""
        if not self._envelopes:
            return
        batch = self._envelopes
        self._envelopes = []
        try:
            response = await self._client.post(self._track_url, json=batch)
            response.raise_for_status()
        except httpx.HTTPError:
            self._envelopes[:0] = batch
            raise
