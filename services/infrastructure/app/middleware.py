import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency in seconds", ["method", "path"]
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records request count and latency labeled by ROUTE TEMPLATE, not the
    raw resolved path -- `/environments/{environment_id}` as one label
    value, not a distinct one per environment id. Identical reasoning to
    every other service's middleware.py (see e.g.
    services/deployment/app/middleware.py) -- duplicated, not shared, same
    as audit_client.py.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            route = request.scope.get("route")
            path_label = route.path if route is not None else "unmatched"
            REQUEST_COUNT.labels(request.method, path_label, status_code).inc()
            REQUEST_LATENCY.labels(request.method, path_label).observe(duration)
