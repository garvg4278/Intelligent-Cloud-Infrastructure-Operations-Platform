from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import get_db
from .middleware import MetricsMiddleware
from .routers import alerts

app = FastAPI(title="ICOP Alert Service", version="0.1.0")
app.add_middleware(MetricsMiddleware)
app.include_router(alerts.router)


@app.get("/health", tags=["ops"])
def health():
    # Deliberately shallow -- this is the LIVENESS probe target (see
    # infra/helm/service-chart/templates/deployment.yaml). Liveness
    # checking a dependency like the database would mean a DB outage
    # fails every pod's liveness at once, restarting all of them
    # simultaneously -- which fixes nothing while the DB is still down
    # and adds a restart storm on top of an existing outage. This only
    # confirms the process itself is alive and answering requests.
    return {"status": "ok", "service": "alert"}


@app.get("/health/ready", tags=["ops"])
def readiness(db: Session = Depends(get_db)):
    # This is the READINESS probe target -- deliberately a deeper check
    # than /health above. A pod that can't reach its database genuinely
    # isn't ready to serve real requests; failing readiness (not
    # liveness) is the correct response, since it pulls this one pod out
    # of the Service's endpoints without restarting it -- traffic stops
    # routing here until the database call below succeeds again, no
    # restart storm, no pretending a DB-less pod can serve real traffic.
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unreachable") from None
    return {"status": "ready", "service": "alert"}


@app.get("/metrics", tags=["ops"])
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
