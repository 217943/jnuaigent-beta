import importlib
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import validate

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "triage_output.schema.json"


def create_client(tmp_path):
    os.environ["TRIAGE_DB_PATH"] = str(tmp_path / "test.db")
    from app import main

    importlib.reload(main)
    return TestClient(main.app)


def load_schema():
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_post_request_returns_triage(tmp_path):
    client = create_client(tmp_path)
    payload = {
        "user_role": "student",
        "modality_pref": "chat",
        "request_text": "수강 신청 관련 상담이 필요합니다.",
        "tools_hint": "none",
    }
    response = client.post("/api/requests", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert "triage" in data
    assert "needs_human_review" in data

    schema = load_schema()
    validate(instance=data["triage"], schema=schema)


def test_post_request_rejects_long_text(tmp_path):
    client = create_client(tmp_path)
    payload = {
        "request_text": "a" * 501,
    }
    response = client.post("/api/requests", json=payload)
    assert response.status_code in {400, 422}
