import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

from .db import get_db, init_db
from .triage import TriageError, triage_request


class TriagePayload(BaseModel):
    case_id: str
    role: Literal["student", "professor", "staff", "other"]
    issue_type: Literal[
        "mental_health",
        "medical",
        "academic",
        "administrative",
        "safety",
        "other",
    ]
    urgency: Literal["low", "medium", "high", "critical"]
    risk_flags: List[
        Literal[
            "self_harm",
            "harm_to_others",
            "severe_distress",
            "medical_emergency",
            "abuse_or_violence",
            "none",
        ]
    ]
    recommended_channel: Literal[
        "campus_counseling",
        "campus_health_center",
        "emergency_services",
        "academic_advising",
        "hr_admin",
        "campus_security",
        "other",
    ]
    needs_followup: bool
    summary_ko: str
    confidence: float = Field(ge=0, le=1)


class RequestCreate(BaseModel):
    request_text: str = Field(min_length=1)
    user_role: Optional[Literal["student", "professor", "staff", "other"]] = None
    modality_pref: Optional[str] = None
    tools_hint: Optional[str] = None


class RequestRecord(BaseModel):
    id: str
    request_text: str
    triage: TriagePayload
    status: Literal["pending", "approved", "rejected"] = "pending"
    note: Optional[str] = None
    created_at: str


class DecisionPayload(BaseModel):
    action: Literal["approve", "reject"]
    final_topic: Optional[TriagePayload.__annotations__["issue_type"]] = None
    final_difficulty: Optional[TriagePayload.__annotations__["urgency"]] = None
    final_handler: Optional[TriagePayload.__annotations__["recommended_channel"]] = None
    note: Optional[str] = None


app = FastAPI(title="AI Clinic Triage MVP API")


@app.on_event("startup")
def prepare_db() -> None:
    init_db()


def serialize_request(row: Dict) -> RequestRecord:
    triage = json.loads(row["triage_json"])
    return RequestRecord(
        id=row["id"],
        request_text=row["request_text"],
        triage=TriagePayload(**triage),
        status=row["status"],
        note=row.get("note"),
        created_at=row["created_at"],
    )


@app.post("/api/requests", response_model=RequestRecord)
def create_request(payload: RequestCreate, db=Depends(get_db)) -> RequestRecord:
    try:
        triage_result = triage_request(payload.request_text, payload.user_role)
    except TriageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    triage_payload = TriagePayload(**triage_result.triage)
    request_id = f"REQ-{uuid.uuid4()}"
    created_at = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute(
            """
            INSERT INTO requests (
                id,
                created_at,
                user_role,
                modality_pref,
                request_text,
                tools_hint,
                status,
                triage_json,
                triage_confidence,
                risk_flags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                created_at,
                payload.user_role,
                payload.modality_pref,
                payload.request_text,
                payload.tools_hint,
                "pending",
                json.dumps(triage_result.triage, ensure_ascii=False),
                triage_result.confidence,
                json.dumps(triage_result.risk_flags, ensure_ascii=False),
            ),
        )
    return RequestRecord(
        id=request_id,
        request_text=payload.request_text,
        triage=triage_payload,
        status="pending",
        created_at=created_at,
    )


@app.get("/api/queue")
def get_queue(
    status: Literal["pending", "approved", "rejected"] = Query("pending"),
    db=Depends(get_db),
) -> List[Dict]:
    rows = db.execute(
        "SELECT id, request_text, status, created_at, triage_json FROM requests WHERE status = ?",
        (status,),
    ).fetchall()
    return [serialize_request(dict(row)).model_dump() for row in rows]


@app.get("/api/requests/{request_id}")
def get_request(request_id: str, db=Depends(get_db)) -> Dict:
    row = db.execute(
        "SELECT id, request_text, status, created_at, triage_json FROM requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    return serialize_request(dict(row)).model_dump()


@app.post("/api/requests/{request_id}/decision")
def post_decision(request_id: str, payload: DecisionPayload, db=Depends(get_db)) -> Dict:
    row = db.execute(
        "SELECT id, triage_json FROM requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")

    triage = json.loads(row["triage_json"])
    if payload.final_topic:
        triage["issue_type"] = payload.final_topic
    if payload.final_difficulty:
        triage["urgency"] = payload.final_difficulty
    if payload.final_handler:
        triage["recommended_channel"] = payload.final_handler

    status = "approved" if payload.action == "approve" else "rejected"
    decision_id = f"DEC-{uuid.uuid4()}"
    decided_at = datetime.now(timezone.utc).isoformat()

    with db:
        db.execute(
            """
            UPDATE requests
            SET status = ?, triage_json = ?, triage_confidence = ?, risk_flags_json = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(triage, ensure_ascii=False),
                triage.get("confidence", 0.5),
                json.dumps(triage.get("risk_flags", []), ensure_ascii=False),
                request_id,
            ),
        )
        db.execute(
            """
            INSERT INTO decisions (
                id,
                request_id,
                decided_at,
                action,
                final_topic,
                final_difficulty,
                final_handler,
                note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                request_id,
                decided_at,
                payload.action,
                payload.final_topic,
                payload.final_difficulty,
                payload.final_handler,
                payload.note,
            ),
        )

    updated = db.execute(
        "SELECT id, request_text, status, created_at, triage_json FROM requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    return serialize_request(dict(updated)).model_dump()


@app.get("/api/export/csv")
def export_csv(
    status: Literal["pending", "approved", "rejected"] = Query("approved"),
    db=Depends(get_db),
) -> Response:
    rows = db.execute(
        "SELECT id, request_text, status, created_at, triage_json FROM requests WHERE status = ?",
        (status,),
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "case_id",
            "role",
            "issue_type",
            "urgency",
            "risk_flags",
            "recommended_channel",
            "needs_followup",
            "summary_ko",
            "confidence",
            "status",
        ]
    )
    for row in rows:
        triage = json.loads(row["triage_json"])
        writer.writerow(
            [
                row["id"],
                triage.get("case_id"),
                triage.get("role"),
                triage.get("issue_type"),
                triage.get("urgency"),
                "|".join(triage.get("risk_flags", [])),
                triage.get("recommended_channel"),
                triage.get("needs_followup"),
                triage.get("summary_ko"),
                triage.get("confidence"),
                row["status"],
            ]
        )

    return Response(content=output.getvalue(), media_type="text/csv")
