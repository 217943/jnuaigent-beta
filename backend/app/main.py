from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from io import StringIO
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.db import get_db, init_db
from app.triage import TriageError, triage_request

app = FastAPI(title="AI Clinic Triage Backend")


class RequestCreate(BaseModel):
    user_role: Optional[str] = Field(default=None)
    modality_pref: Optional[str] = Field(default=None)
    request_text: str = Field(min_length=1, max_length=500)
    tools_hint: Optional[str] = Field(default=None)


class RequestResponse(BaseModel):
    request_id: str
    triage: dict
    needs_human_review: bool


class DecisionCreate(BaseModel):
    action: str = Field(pattern="^(approve|reject|edit)$")
    final_topic: Optional[str] = Field(default=None)
    final_difficulty: Optional[str] = Field(default=None)
    final_handler: Optional[str] = Field(default=None)
    note: Optional[str] = Field(default=None)


@app.on_event("startup")
def startup() -> None:
    init_db()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_status(action: str) -> str:
    if action == "approve":
        return "approved"
    if action == "reject":
        return "rejected"
    return "pending"


@app.post("/api/requests", response_model=RequestResponse)
def create_request(payload: RequestCreate, db=Depends(get_db)) -> RequestResponse:
    if len(payload.request_text) > 500:
        raise HTTPException(status_code=400, detail="request_text exceeds 500 characters")

    try:
        triage_result = triage_request(payload.request_text, payload.user_role)
    except TriageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    request_id = str(uuid.uuid4())
    created_at = now_iso()
    triage_json = json.dumps(triage_result.triage, ensure_ascii=False)
    risk_flags_json = json.dumps(
        {
            "risk_flags": triage_result.risk_flags,
            "pii_flags": triage_result.pii_flags,
        },
        ensure_ascii=False,
    )
    with db:
        db.execute(
            """
            INSERT INTO requests (
                id, created_at, user_role, modality_pref, request_text, tools_hint,
                status, triage_json, triage_confidence, risk_flags_json
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
                triage_json,
                triage_result.confidence,
                risk_flags_json,
            ),
        )

    return RequestResponse(
        request_id=request_id,
        triage=triage_result.triage,
        needs_human_review=triage_result.needs_human_review,
    )


@app.get("/api/requests/{request_id}")
def get_request(request_id: str, db=Depends(get_db)) -> dict:
    row = db.execute(
        "SELECT * FROM requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")

    triage = json.loads(row["triage_json"])
    needs_human_review = triage.get("confidence", 1.0) < 0.65 or triage.get("risk_flags") != ["none"]
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "user_role": row["user_role"],
        "modality_pref": row["modality_pref"],
        "request_text": row["request_text"],
        "tools_hint": row["tools_hint"],
        "status": row["status"],
        "triage": triage,
        "triage_confidence": row["triage_confidence"],
        "risk_flags": json.loads(row["risk_flags_json"]),
        "needs_human_review": needs_human_review,
    }


@app.get("/api/queue")
def get_queue(status: str = Query(default="pending"), db=Depends(get_db)) -> List[dict]:
    rows = db.execute(
        "SELECT * FROM requests WHERE status = ? ORDER BY created_at ASC",
        (status,),
    ).fetchall()
    response = []
    for row in rows:
        triage = json.loads(row["triage_json"])
        needs_human_review = triage.get("confidence", 1.0) < 0.65 or triage.get("risk_flags") != ["none"]
        response.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "user_role": row["user_role"],
                "modality_pref": row["modality_pref"],
                "request_text": row["request_text"],
                "status": row["status"],
                "triage": triage,
                "needs_human_review": needs_human_review,
            }
        )
    return response


@app.post("/api/requests/{request_id}/decision")
def create_decision(request_id: str, payload: DecisionCreate, db=Depends(get_db)) -> dict:
    row = db.execute(
        "SELECT id FROM requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")

    decision_id = str(uuid.uuid4())
    decided_at = now_iso()
    status = map_status(payload.action)

    with db:
        db.execute(
            """
            INSERT INTO decisions (
                id, request_id, decided_at, action, final_topic,
                final_difficulty, final_handler, note
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
        db.execute(
            "UPDATE requests SET status = ? WHERE id = ?",
            (status, request_id),
        )

    return {
        "decision_id": decision_id,
        "request_id": request_id,
        "status": status,
    }


@app.get("/api/export/csv")
def export_csv(status: str = Query(default="approved"), db=Depends(get_db)) -> Response:
    rows = db.execute(
        """
        SELECT
            requests.*, decisions.action AS decision_action,
            decisions.final_topic, decisions.final_difficulty,
            decisions.final_handler, decisions.note
        FROM requests
        LEFT JOIN decisions ON decisions.request_id = requests.id
        WHERE requests.status = ?
        ORDER BY requests.created_at ASC
        """,
        (status,),
    ).fetchall()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "request_id",
            "created_at",
            "user_role",
            "modality_pref",
            "request_text",
            "status",
            "triage_json",
            "triage_confidence",
            "risk_flags_json",
            "decision_action",
            "final_topic",
            "final_difficulty",
            "final_handler",
            "note",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["created_at"],
                row["user_role"],
                row["modality_pref"],
                row["request_text"],
                row["status"],
                row["triage_json"],
                row["triage_confidence"],
                row["risk_flags_json"],
                row["decision_action"],
                row["final_topic"],
                row["final_difficulty"],
                row["final_handler"],
                row["note"],
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=export.csv"},
    )
