from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base


def create_test_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_create_request_and_triage_schema():
    client = create_test_client()
    payload = {
        "user_role": "student",
        "modality_pref": "text",
        "request_text": "데이터 분석을 위한 리포트 요청입니다.",
        "tools_hint": "tableau",
    }

    response = client.post("/api/requests", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "request_id" in data
    assert "triage" in data

    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "triage_output.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data["triage"], schema=schema)
