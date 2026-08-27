from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.cors import CORSMiddleware

from .config import settings
from .core.http_client import close_http_client
from .middleware.correlation_id import CorrelationIdMiddleware
from .middleware.metrics import MetricsMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.security_headers import SecurityHeadersMiddleware
from .routers import proxy


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_http_client()


app = FastAPI(title="ICOP API Gateway", version="0.1.0", lifespan=lifespan)

# NOTE on ordering: Starlette wraps the LAST middleware added as the
# OUTERMOST layer (verified with a test, not assumed -- see
# test_correlation_id_present_even_on_rate_limited_response). Stack here,
# outermost first: SecurityHeaders -> CORS -> Metrics -> CorrelationId ->
# RateLimit -> app.
#
# SecurityHeaders outermost so every response gets the headers, including
# a 429/401/500 that never reaches the app itself.
#
# CORS next-outermost because CORSMiddleware has to intercept a browser's
# OPTIONS preflight request itself, before rate limiting or
# app/security.py's authentication dependency ever see it -- a legitimate
# cross-origin preflight (no Authorization header at all; browsers don't
# send one on preflight) must never be rate-limited or, worse, rejected as
# unauthenticated. The actual follow-up request (the real GET/POST, with
# the real Authorization header) still passes through every layer beneath
# CORS normally -- CORS only special-cases OPTIONS.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(proxy.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    correlation_id = getattr(request.state, "correlation_id", None)
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "correlation_id": correlation_id},
    )


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "service": "gateway"}


@app.get("/health/ready", tags=["ops"])
def readiness():
    # Deliberately an alias of /health, not a deep check -- unlike the 8
    # database-backed services (see e.g. services/auth/app/main.py for
    # the pattern this deviates from), the gateway has no single
    # dependency whose failure should pull it out of rotation. Redis
    # (rate limiting) fails open by design now (see
    # app/middleware/rate_limit.py) specifically so a Redis outage
    # degrades this gateway, not takes it down -- marking it "not ready"
    # over that same outage would contradict the whole point of having
    # made it fail open in the first place. Still a real endpoint the
    # Helm chart's readinessProbe can point at (every service needs one
    # at the same path -- see infra/helm/service-chart/values.yaml), just
    # an honestly shallow one.
    return {"status": "ready", "service": "gateway"}


@app.get("/metrics", tags=["ops"])
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
