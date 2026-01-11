from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import engine, get_db
from app.triage.triage import triage, triage_to_json

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Jnuaigent Backend")


@app.post("/api/requests", response_model=schemas.CreateRequestResponse)
def create_request(payload: schemas.RequestCreate, db: Session = Depends(get_db)):
    if len(payload.request_text) > 500:
        raise HTTPException(status_code=400, detail="request_text too long")

    triage_result = triage(payload.request_text)
    triage_json = triage_to_json(triage_result)
    risk_flags_json = json.dumps(triage_result.risk_flags, ensure_ascii=False)

    request = models.Request(
        user_role=payload.user_role,
        modality_pref=payload.modality_pref,
        request_text=payload.request_text,
        tools_hint=payload.tools_hint,
        status="pending",
        triage_json=triage_json,
        triage_confidence=triage_result.confidence,
        risk_flags_json=risk_flags_json,
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    return schemas.CreateRequestResponse(request_id=request.id, triage=triage_result)


@app.get("/api/requests/{request_id}", response_model=schemas.RequestResponse)
def get_request(request_id: str, db: Session = Depends(get_db)):
    request = (
        db.query(models.Request)
        .filter(models.Request.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    triage_data = json.loads(request.triage_json)
    decision = request.decision

    decision_payload = None
    if decision:
        decision_payload = schemas.DecisionResponse(
            id=decision.id,
            decided_at=decision.decided_at,
            action=decision.action,
            final_topic=decision.final_topic,
            final_difficulty=decision.final_difficulty,
            final_handler=decision.final_handler,
            note=decision.note,
        )

    return schemas.RequestResponse(
        id=request.id,
        created_at=request.created_at,
        user_role=request.user_role,
        modality_pref=request.modality_pref,
        request_text=request.request_text,
        tools_hint=request.tools_hint,
        status=request.status,
        triage=schemas.TriageResult(**triage_data),
        decision=decision_payload,
    )


@app.get("/api/queue", response_model=list[schemas.RequestSummary])
def list_queue(
    status: str = Query("pending"), db: Session = Depends(get_db)
):
    requests = (
        db.query(models.Request)
        .filter(models.Request.status == status)
        .order_by(models.Request.created_at.asc())
        .all()
    )
    summaries: list[schemas.RequestSummary] = []
    for req in requests:
        triage_data = json.loads(req.triage_json)
        summaries.append(
            schemas.RequestSummary(
                id=req.id,
                created_at=req.created_at,
                user_role=req.user_role,
                modality_pref=req.modality_pref,
                status=req.status,
                triage_confidence=req.triage_confidence,
                needs_human_review=triage_data.get("needs_human_review", False),
            )
        )
    return summaries


@app.post("/api/requests/{request_id}/decision", response_model=schemas.DecisionResponse)
def decide_request(
    request_id: str, payload: schemas.DecisionCreate, db: Session = Depends(get_db)
):
    request = (
        db.query(models.Request)
        .filter(models.Request.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    action = payload.action.lower()
    if action not in {"approve", "reject", "edit"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    decision = models.Decision(
        request_id=request.id,
        action=action,
        final_topic=payload.final_topic,
        final_difficulty=payload.final_difficulty,
        final_handler=payload.final_handler,
        note=payload.note,
    )
    db.add(decision)

    if action == "reject":
        request.status = "rejected"
    else:
        request.status = "approved"

    db.commit()
    db.refresh(decision)

    return schemas.DecisionResponse(
        id=decision.id,
        decided_at=decision.decided_at,
        action=decision.action,
        final_topic=decision.final_topic,
        final_difficulty=decision.final_difficulty,
        final_handler=decision.final_handler,
        note=decision.note,
    )


@app.get("/api/export/csv")
def export_csv(
    status: str = Query("approved"), db: Session = Depends(get_db)
):
    requests = (
        db.query(models.Request)
        .filter(models.Request.status == status)
        .order_by(models.Request.created_at.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "request_id",
            "created_at",
            "user_role",
            "modality_pref",
            "request_text",
            "tools_hint",
            "status",
            "triage_topic",
            "triage_difficulty",
            "triage_handler",
            "decision_action",
            "decision_topic",
            "decision_difficulty",
            "decision_handler",
            "decision_note",
        ]
    )

    for req in requests:
        triage_data = json.loads(req.triage_json)
        decision = req.decision
        writer.writerow(
            [
                req.id,
                req.created_at.isoformat(),
                req.user_role,
                req.modality_pref,
                req.request_text,
                req.tools_hint,
                req.status,
                triage_data.get("topic"),
                triage_data.get("difficulty"),
                triage_data.get("handler"),
                decision.action if decision else None,
                decision.final_topic if decision else None,
                decision.final_difficulty if decision else None,
                decision.final_handler if decision else None,
                decision.note if decision else None,
            ]
        )

    output.seek(0)
    filename = f"requests_{status}_{datetime.utcnow().date().isoformat()}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(iter([output.getvalue()]), headers=headers, media_type="text/csv")
