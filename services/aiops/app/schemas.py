from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExplainRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=255)
    question: str = Field(min_length=1, max_length=2000)


class EvidenceItem(BaseModel):
    tool: str
    input: dict
    result: dict


class ExplainResponse(BaseModel):
    answer: str
    evidence: list[EvidenceItem]
    iterations: int


class AIQueryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    service_name: str
    question: str
    answer: str
    iterations: int
    created_at: datetime


class AIQueryDetailOut(AIQueryOut):
    evidence: list[EvidenceItem]
