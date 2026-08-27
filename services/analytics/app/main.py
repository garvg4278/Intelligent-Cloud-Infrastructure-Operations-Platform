from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .middleware import MetricsMiddleware
from .routers import analytics

app = FastAPI(title="ICOP Analytics Service", version="0.1.0")
app.add_middleware(MetricsMiddleware)
app.include_router(analytics.router)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "service": "analytics"}


@app.get("/health/ready", tags=["ops"])
def readiness():
    # Deliberately an alias of /health, not a deep check -- same
    # reasoning as services/gateway/app/main.py's identical choice.
    # Analytics has no database of its own and already degrades
    # per-section when deployment/incident/alert are unreachable (see
    # routers/analytics.py's overview_report) rather than failing
    # outright -- there's no single dependency whose outage should pull
    # this pod out of rotation entirely.
    return {"status": "ready", "service": "analytics"}


@app.get("/metrics", tags=["ops"])
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
