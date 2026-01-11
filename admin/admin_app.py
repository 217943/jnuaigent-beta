import json
import os
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def show_password_gate() -> bool:
    if not ADMIN_PASSWORD:
        st.warning("ADMIN_PASSWORD가 설정되지 않았습니다. 로컬 개발 환경에서만 사용하세요.")
        return True

    if st.session_state.get("is_authenticated"):
        return True

    st.subheader("관리자 로그인")
    password = st.text_input("관리자 비밀번호", type="password")
    if st.button("로그인"):
        if password == ADMIN_PASSWORD:
            st.session_state["is_authenticated"] = True
            st.success("로그인 완료")
            return True
        st.error("비밀번호가 올바르지 않습니다.")
    return False


def fetch_queue(status: str = "pending") -> List[Dict[str, Any]]:
    response = requests.get(f"{BACKEND_URL}/api/queue", params={"status": status}, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_request(request_id: str) -> Dict[str, Any]:
    response = requests.get(f"{BACKEND_URL}/api/requests/{request_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def post_decision(request_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(
        f"{BACKEND_URL}/api/requests/{request_id}/decision",
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def render_badges(triage: Dict[str, Any]) -> None:
    topic = triage.get("issue_type", "unknown")
    difficulty = triage.get("urgency", "unknown")
    risk_flags = triage.get("risk_flags", [])
    confidence = triage.get("confidence", "-")
    badges = [
        f"topic:{topic}",
        f"difficulty:{difficulty}",
        f"risk:{','.join(risk_flags) if risk_flags else 'none'}",
        f"confidence:{confidence}",
    ]
    st.markdown(" ".join(f"`{badge}`" for badge in badges))


def build_note(rationale: str, reply_draft: str) -> str:
    note = {
        "rationale": rationale.strip(),
        "user_reply_draft": reply_draft.strip(),
    }
    return json.dumps(note, ensure_ascii=False)


st.set_page_config(page_title="AI Clinic Admin", layout="wide")
st.title("AI Clinic Triage Admin")

if not show_password_gate():
    st.stop()

st.caption(f"Backend: {BACKEND_URL}")

st.header("Review Queue")
queue_error: Optional[str] = None
queue_items: List[Dict[str, Any]] = []
try:
    queue_items = fetch_queue()
except requests.RequestException as exc:
    queue_error = str(exc)

if queue_error:
    st.error(f"Queue를 불러오지 못했습니다: {queue_error}")

selected_request_id = st.session_state.get("selected_request_id")

if queue_items:
    st.subheader("Pending requests")
    for item in queue_items:
        with st.expander(f"{item['id']} · {item['request_text'][:40]}"):
            render_badges(item.get("triage", {}))
            if st.button("상세 보기", key=f"select_{item['id']}"):
                st.session_state["selected_request_id"] = item["id"]
                selected_request_id = item["id"]

if not selected_request_id and queue_items:
    selected_request_id = queue_items[0]["id"]
    st.session_state["selected_request_id"] = selected_request_id

if not queue_items:
    st.info("현재 대기 중인 요청이 없습니다.")

if selected_request_id:
    st.header("Request Detail")
    request_error: Optional[str] = None
    request_detail: Dict[str, Any] = {}
    try:
        request_detail = fetch_request(selected_request_id)
    except requests.RequestException as exc:
        request_error = str(exc)

    if request_error:
        st.error(f"요청을 불러오지 못했습니다: {request_error}")
    else:
        triage = request_detail.get("triage", {})
        if st.session_state.get("loaded_request_id") != selected_request_id:
            st.session_state["loaded_request_id"] = selected_request_id
            st.session_state["rationale"] = triage.get("summary_ko", "")
            st.session_state["user_reply_draft"] = ""
            st.session_state["final_topic"] = triage.get("issue_type", "")
            st.session_state["final_difficulty"] = triage.get("urgency", "")
            st.session_state["final_handler"] = triage.get("recommended_channel", "")
        st.subheader("Request text")
        st.text_area("요청 내용", value=request_detail.get("request_text", ""), height=160, disabled=True)

        st.subheader("Triage JSON")
        st.json(triage)

        st.subheader("Rationale")
        rationale = st.text_area(
            "분류 근거",
            value=st.session_state.get("rationale", ""),
            height=120,
        )
        st.session_state["rationale"] = rationale

        st.subheader("User reply draft")
        reply_draft = st.text_area(
            "응답 초안",
            value=st.session_state.get("user_reply_draft", ""),
            height=120,
        )
        st.session_state["user_reply_draft"] = reply_draft

        st.subheader("Edit fields")
        final_topic = st.text_input(
            "최종 토픽",
            value=st.session_state.get("final_topic", ""),
        )
        final_difficulty = st.text_input(
            "최종 난이도",
            value=st.session_state.get("final_difficulty", ""),
        )
        final_handler = st.text_input(
            "최종 담당 채널",
            value=st.session_state.get("final_handler", ""),
        )
        st.session_state["final_topic"] = final_topic
        st.session_state["final_difficulty"] = final_difficulty
        st.session_state["final_handler"] = final_handler

        note_payload = build_note(rationale, reply_draft)

        st.subheader("Actions")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Approve"):
                try:
                    post_decision(
                        selected_request_id,
                        {
                            "action": "approve",
                            "note": note_payload,
                        },
                    )
                    st.success("승인 완료")
                    st.session_state.pop("selected_request_id", None)
                except requests.RequestException as exc:
                    st.error(f"승인 실패: {exc}")
        with col2:
            if st.button("Edit + Approve"):
                try:
                    post_decision(
                        selected_request_id,
                        {
                            "action": "approve",
                            "final_topic": final_topic or None,
                            "final_difficulty": final_difficulty or None,
                            "final_handler": final_handler or None,
                            "note": note_payload,
                        },
                    )
                    st.success("수정 후 승인 완료")
                    st.session_state.pop("selected_request_id", None)
                except requests.RequestException as exc:
                    st.error(f"수정 승인 실패: {exc}")
        with col3:
            if st.button("Reject"):
                try:
                    post_decision(
                        selected_request_id,
                        {
                            "action": "reject",
                            "note": note_payload,
                        },
                    )
                    st.success("거절 완료")
                    st.session_state.pop("selected_request_id", None)
                except requests.RequestException as exc:
                    st.error(f"거절 실패: {exc}")

st.header("Exports")
if st.button("Download approved CSV"):
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/export/csv",
            params={"status": "approved"},
            timeout=15,
        )
        response.raise_for_status()
        st.download_button(
            "CSV 다운로드",
            data=response.content,
            file_name="approved_export.csv",
            mime="text/csv",
        )
    except requests.RequestException as exc:
        st.error(f"CSV 다운로드 실패: {exc}")
