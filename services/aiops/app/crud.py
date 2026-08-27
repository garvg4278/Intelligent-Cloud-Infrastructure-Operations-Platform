import json

from sqlalchemy.orm import Session

from . import models
from .agent import AgentResult


def log_query(db: Session, service_name: str, question: str, result: AgentResult) -> models.AIQuery:
    record = models.AIQuery(
        service_name=service_name,
        question=question,
        answer=result.answer,
        evidence_json=json.dumps(result.evidence),
        iterations=result.iterations,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_query(db: Session, query_id: str) -> models.AIQuery | None:
    return db.query(models.AIQuery).filter(models.AIQuery.id == query_id).first()


def list_queries(db: Session, service_name: str | None = None) -> list[models.AIQuery]:
    query = db.query(models.AIQuery)
    if service_name:
        query = query.filter(models.AIQuery.service_name == service_name)
    return query.order_by(models.AIQuery.created_at.desc()).all()


def evidence_of(record: models.AIQuery) -> list[dict]:
    return json.loads(record.evidence_json)
