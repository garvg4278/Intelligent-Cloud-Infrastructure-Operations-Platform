import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AIQuery(Base):
    """A logged record of one explain request -- question in, evidence
    gathered, answer out. Kept for the same reason audit_events exist in
    the original design: 'immutable history should be preserved,' and an
    AI-generated explanation someone acted on is exactly the kind of
    thing worth being able to look back at.
    """

    __tablename__ = "ai_queries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_name = Column(String(255), nullable=False, index=True)
    question = Column(String(2000), nullable=False)
    answer = Column(Text, nullable=False)
    # JSON-encoded list of {tool, input, result} -- the full evidence
    # trail behind `answer`, stored as text rather than a real JSON column
    # so this works identically on SQLite (tests) and Postgres (prod)
    # without a dialect-specific type.
    evidence_json = Column(Text, nullable=False)
    iterations = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
