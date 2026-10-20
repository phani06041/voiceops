from pydantic import BaseModel, Field
from typing import Any

class CaseQuery(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

class StatusUpdate(BaseModel):
    status: str
    reason: str = Field(min_length=2, max_length=1000)

class ReviewerNote(BaseModel):
    note: str = Field(min_length=1, max_length=3000)

class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

class QueryResponse(BaseModel):
    answer: str
    case_id: str | None = None
    evidence: list[str] = []
    recommended_action: str | None = None
    requires_review: bool = False
