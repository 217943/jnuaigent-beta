from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RequestCreate(BaseModel):
    user_role: str | None = None
    modality_pref: str | None = None
    request_text: str = Field(..., max_length=500)
    tools_hint: str | None = None


class TriageResult(BaseModel):
    topic: str
    difficulty: str
    handler: str
    confidence: float
    risk_flags: dict[str, bool]
    needs_human_review: bool
    rationale: str
    suggested_edits: list[str]


class RequestResponse(BaseModel):
    id: str
    created_at: datetime
    user_role: str | None
    modality_pref: str | None
    request_text: str
    tools_hint: str | None
    status: str
    triage: TriageResult
    decision: "DecisionResponse | None" = None


class DecisionCreate(BaseModel):
    action: str
    final_topic: str | None = None
    final_difficulty: str | None = None
    final_handler: str | None = None
    note: str | None = None


class DecisionResponse(BaseModel):
    id: str
    decided_at: datetime
    action: str
    final_topic: str | None
    final_difficulty: str | None
    final_handler: str | None
    note: str | None


class RequestSummary(BaseModel):
    id: str
    created_at: datetime
    user_role: str | None
    modality_pref: str | None
    status: str
    triage_confidence: float
    needs_human_review: bool


class CreateRequestResponse(BaseModel):
    request_id: str
    triage: TriageResult


class ExportRow(BaseModel):
    request_id: str
    created_at: datetime
    user_role: str | None
    modality_pref: str | None
    request_text: str
    tools_hint: str | None
    status: str
    triage_topic: str
    triage_difficulty: str
    triage_handler: str
    decision_action: str | None
    decision_topic: str | None
    decision_difficulty: str | None
    decision_handler: str | None
    decision_note: str | None


RequestResponse.model_rebuild()
