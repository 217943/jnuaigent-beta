from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from app.schemas import TriageResult

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"\b(?:\+?82\s?)?(?:0\d{1,2}[-\s]?)?\d{3,4}[-\s]?\d{4}\b")


@dataclass
class RuleMatch:
    topic: str
    difficulty: str
    handler: str
    rationale: str


KEYWORD_RULES: list[tuple[list[str], RuleMatch]] = [
    (
        ["데이터", "분석", "통계", "리포트", "시각화"],
        RuleMatch("data", "medium", "analytics_team", "데이터/분석 키워드 감지"),
    ),
    (
        ["보안", "개인정보", "PII", "암호화", "접근제어"],
        RuleMatch("security", "high", "security_team", "보안 관련 요청"),
    ),
    (
        ["마케팅", "홍보", "캠페인", "콘텐츠", "SNS"],
        RuleMatch("marketing", "medium", "growth_team", "마케팅/콘텐츠 키워드 감지"),
    ),
    (
        ["과제", "강의", "교육", "연구", "논문"],
        RuleMatch("academic", "medium", "education_team", "교육/연구 관련 키워드"),
    ),
]

RISK_KEYWORDS = {
    "violence": ["폭력", "위협", "살해", "자해"],
    "medical": ["진단", "처방", "의료", "병원"],
    "finance": ["투자", "대출", "금융", "카드번호"],
}


def detect_pii(text: str) -> bool:
    return bool(EMAIL_PATTERN.search(text) or PHONE_PATTERN.search(text))


def rule_based_triage(text: str) -> TriageResult:
    lowered = text.lower()
    match = RuleMatch("general", "low", "general_queue", "기본 분류")
    confidence = 0.5

    for keywords, rule in KEYWORD_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            match = rule
            confidence = 0.75
            break

    risk_flags = {key: False for key in RISK_KEYWORDS}
    for key, keywords in RISK_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            risk_flags[key] = True

    pii_detected = detect_pii(text)
    risk_flags["pii_detected"] = pii_detected

    if pii_detected or any(risk_flags.values()):
        confidence = min(confidence, 0.6)

    needs_human_review = any(risk_flags.values()) or confidence < 0.65

    return TriageResult(
        topic=match.topic,
        difficulty=match.difficulty,
        handler=match.handler,
        confidence=round(confidence, 2),
        risk_flags=risk_flags,
        needs_human_review=needs_human_review,
        rationale=match.rationale,
        suggested_edits=["민감 정보(이메일/전화번호)를 제거하세요"]
        if pii_detected
        else [],
    )


def openai_triage(text: str) -> TriageResult:
    _ = text
    raise RuntimeError("OpenAI triage placeholder")


def triage(text: str) -> TriageResult:
    if os.getenv("OPENAI_API_KEY"):
        try:
            return openai_triage(text)
        except Exception:
            return rule_based_triage(text)
    return rule_based_triage(text)


def triage_to_json(result: TriageResult) -> str:
    return json.dumps(result.model_dump(), ensure_ascii=False)
