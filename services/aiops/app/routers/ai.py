from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..agent import NoLLMConfiguredError, run_agent
from ..config import settings
from ..database import get_db
from ..llm_client import get_llm_client
from ..service_clients import get_alert_client, get_deployment_client, get_incident_client, get_metrics_client
from ..tools import ToolExecutor

router = APIRouter(prefix="/ai", tags=["ai"])


def _build_tool_executor() -> ToolExecutor:
    return ToolExecutor(
        deployment_client=get_deployment_client(),
        alert_client=get_alert_client(),
        incident_client=get_incident_client(),
        metrics_client=get_metrics_client(),
    )


@router.post("/explain", response_model=schemas.ExplainResponse)
def explain(payload: schemas.ExplainRequest, db: Session = Depends(get_db)):
    try:
        result = run_agent(
            question=payload.question,
            service_name=payload.service_name,
            llm_client=get_llm_client(),
            tool_executor=_build_tool_executor(),
            max_iterations=settings.MAX_AGENT_ITERATIONS,
        )
    except NoLLMConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    crud.log_query(db, payload.service_name, payload.question, result)
    return schemas.ExplainResponse(
        answer=result.answer, evidence=result.evidence, iterations=result.iterations
    )


@router.get("/history", response_model=list[schemas.AIQueryOut])
def list_history(service_name: str | None = None, db: Session = Depends(get_db)):
    return crud.list_queries(db, service_name=service_name)


@router.get("/history/{query_id}", response_model=schemas.AIQueryDetailOut)
def get_history_item(query_id: str, db: Session = Depends(get_db)):
    record = crud.get_query(db, query_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="query not found")
    out = schemas.AIQueryOut.model_validate(record).model_dump()
    return schemas.AIQueryDetailOut(**out, evidence=crud.evidence_of(record))
