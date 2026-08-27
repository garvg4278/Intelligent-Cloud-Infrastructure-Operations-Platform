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
    raw resolved path -- `/deployments/{deployment_id}` as one label value,
    not a distinct one per deployment id, which would make the metric's
    cardinality grow without bound. The route template is only available on
    request.scope AFTER routing has happened, i.e. after call_next()
    returns (verified empirically, not assumed) -- for a path that doesn't
    match any route at all, it falls back to a fixed "unmatched" label
    rather than the raw path, for the same cardinality reason.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        # BaseHTTPMiddleware's call_next re-raises any exception from
        # downstream after capturing it -- without try/finally here, a
        # request that ends in an unhandled exception would skip metric
        # recording entirely, which is exactly the requests you most want
        # counted (error rate is one of the most-referenced metrics in the
        # design doc). status_code defaults to 500 for that case.
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
