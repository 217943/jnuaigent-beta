from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from jsonschema import validate
from jsonschema.exceptions import ValidationError

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "triage_output.schema.json"

ROLE_OPTIONS = {"student", "professor", "staff", "other"}
ISSUE_TYPES = {
    "mental_health",
    "medical",
    "academic",
    "administrative",
    "safety",
    "other",
}
URGENCY_LEVELS = {"low", "medium", "high", "critical"}

KEYWORDS = {
    "mental_health": ["불안", "우울", "스트레스", "panic", "anxiety", "depress"],
    "medical": ["통증", "병원", "다쳤", "부상", "화상", "기절", "응급"],
    "academic": ["수강", "성적", "학점", "졸업", "전공", "과제"],
    "administrative": ["등록", "휴학", "복학", "증명서", "연차", "급여"],
    "safety": ["위협", "폭력", "괴롭힘", "스토킹", "침입"],
}

RISK_KEYWORDS = {
    "self_harm": ["자살", "죽고", "self-harm", "극단"],
    "harm_to_others": ["해치", "살해", "폭행"],
    "severe_distress": ["공황", "극심", "패닉"],
    "medical_emergency": ["응급", "의식 잃", "호흡"],
    "abuse_or_violence": ["폭력", "학대", "성추행", "성폭력"],
}

PII_PATTERNS = {
    "student_id": re.compile(r"\b\d{7,10}\b"),
    "phone": re.compile(r"\b01[0-9]-?\d{3,4}-?\d{4}\b"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}

PII_KEYWORDS = {
    "grades": ["학점", "성적", "GPA"],
    "address": ["주소", "기숙사", "아파트", "동", "호"],
    "recording": ["녹음", "촬영", "recording", "영상"],
}


@dataclass
class TriageResult:
    triage: Dict[str, object]
    confidence: float
    risk_flags: List[str]
    pii_flags: List[str]
    needs_human_review: bool


class TriageError(RuntimeError):
    pass


def load_schema() -> Dict[str, object]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def detect_keywords(text: str, mapping: Dict[str, List[str]]) -> str | None:
    lowered = text.lower()
    for category, keywords in mapping.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                return category
    return None


def detect_risk_flags(text: str) -> List[str]:
    lowered = text.lower()
    flags: List[str] = []
    for flag, keywords in RISK_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                flags.append(flag)
                break
    return flags


def detect_pii(text: str) -> List[str]:
    hits: List[str] = []
    for label, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            hits.append(label)
    lowered = text.lower()
    for label, keywords in PII_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            hits.append(label)
    return sorted(set(hits))


def derive_urgency(text: str, risk_flags: List[str]) -> str:
    lowered = text.lower()
    if "응급" in lowered or "즉시" in lowered or "emergency" in lowered:
        return "critical"
    if any(flag in {"self_harm", "harm_to_others", "medical_emergency"} for flag in risk_flags):
        return "critical"
    if "긴급" in lowered or risk_flags:
        return "high"
    if "빠른" in lowered or "soon" in lowered:
        return "medium"
    return "low"


def derive_channel(issue_type: str, urgency: str, risk_flags: List[str]) -> str:
    if urgency == "critical":
        if "medical_emergency" in risk_flags:
            return "emergency_services"
        if "harm_to_others" in risk_flags:
            return "campus_security"
    mapping = {
        "mental_health": "campus_counseling",
        "medical": "campus_health_center",
        "academic": "academic_advising",
        "administrative": "hr_admin",
        "safety": "campus_security",
    }
    return mapping.get(issue_type, "other")


def compute_confidence(issue_type: str, risk_flags: List[str], pii_flags: List[str]) -> float:
    confidence = 0.78
    if issue_type == "other":
        confidence -= 0.15
    if risk_flags:
        confidence -= 0.05
    if pii_flags:
        confidence -= 0.08
    return max(0.4, min(0.95, confidence))


def openai_triage(_: str, user_role: str | None) -> TriageResult:
    raise TriageError("OPENAI_API_KEY not configured")


def rule_based_triage(text: str, user_role: str | None) -> TriageResult:
    role = user_role if user_role in ROLE_OPTIONS else "other"
    issue_type = detect_keywords(text, KEYWORDS) or "other"
    risk_flags = detect_risk_flags(text)
    urgency = derive_urgency(text, risk_flags)
    pii_flags = detect_pii(text)
    confidence = compute_confidence(issue_type, risk_flags, pii_flags)
    recommended_channel = derive_channel(issue_type, urgency, risk_flags)
    if not risk_flags:
        risk_flags = ["none"]
    needs_followup = urgency in {"high", "critical"} or risk_flags != ["none"]
    triage = {
        "case_id": str(uuid.uuid4()),
        "role": role,
        "issue_type": issue_type,
        "urgency": urgency,
        "risk_flags": risk_flags,
        "recommended_channel": recommended_channel,
        "needs_followup": needs_followup,
        "summary_ko": "분류 목적으로 제출된 문의로 주요 범주를 지정함.",
        "confidence": confidence,
    }
    needs_human_review = risk_flags != ["none"] or confidence < 0.65
    return TriageResult(triage, confidence, risk_flags, pii_flags, needs_human_review)


def triage_request(text: str, user_role: str | None) -> TriageResult:
    if os.getenv("OPENAI_API_KEY"):
        try:
            result = openai_triage(text, user_role)
        except TriageError:
            result = rule_based_triage(text, user_role)
    else:
        result = rule_based_triage(text, user_role)

    schema = load_schema()
    try:
        validate(instance=result.triage, schema=schema)
    except ValidationError as exc:
        raise TriageError(f"Triage output failed schema validation: {exc.message}") from exc
    return result
