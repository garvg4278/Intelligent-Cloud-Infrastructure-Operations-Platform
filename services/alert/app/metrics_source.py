"""Queries Prometheus for a current metric value. Sync httpx (not async) on
purpose: this only ever runs inside a Celery task, same reasoning as the
deployment service's HelmOrchestrator using sync subprocess.
"""

from __future__ import annotations

from typing import Protocol

import httpx


class MetricsQueryError(Exception):
    pass


class MetricsSource(Protocol):
    def query(self, promql: str) -> float: ...


class PrometheusMetricsSource:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def query(self, promql: str) -> float:
        try:
            resp = httpx.get(f"{self.base_url}/api/v1/query", params={"query": promql}, timeout=10)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise MetricsQueryError(f"prometheus query failed: {exc}") from exc

        data = resp.json()
        if data.get("status") != "success":
            raise MetricsQueryError(f"prometheus returned a non-success status: {data}")

        result = data.get("data", {}).get("result", [])
        if not result:
            raise MetricsQueryError(f"no data returned for query: {promql!r}")

        try:
            # Prometheus's instant-query response shape:
            # data.result[0].value == [unix_timestamp, "value_as_string"]
            return float(result[0]["value"][1])
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise MetricsQueryError(f"unexpected prometheus response shape: {data}") from exc


_metrics_source: MetricsSource | None = None


def get_metrics_source() -> MetricsSource:
    global _metrics_source
    if _metrics_source is None:
        from .config import settings

        _metrics_source = PrometheusMetricsSource(settings.PROMETHEUS_URL)
    return _metrics_source


def set_metrics_source(source: MetricsSource | None) -> None:
    """Test hook."""
    global _metrics_source
    _metrics_source = source
