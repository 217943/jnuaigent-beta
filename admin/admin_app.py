import json
import os
from datetime import datetime

import requests
import streamlit as st


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

KNOWN_RISK_FLAGS = ["pii", "self_harm", "legal", "medical", "finance", "other"]
FINAL_HANDLERS = ["tutor", "consultant", "hybrid"]


st.set_page_config(page_title="Admin Review", layout="wide")


def require_password() -> None:
    if not ADMIN_PASSWORD:
        st.warning(
            "ADMIN_PASSWORD is not set. Running in open mode for local development.",
            icon="⚠️",
        )
        return

    if st.session_state.get("authed"):
        return

    st.info("Enter admin password to continue.")
    password = st.text_input("Admin password", type="password")
    if st.button("Unlock"):
        if password == ADMIN_PASSWORD:
            st.session_state.authed = True
            st.experimental_rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


def request_json(method: str, path: str, payload: dict | None = None):
    url = f"{BACKEND_URL}{path}"
    try:
        response = requests.request(method, url, json=payload, timeout=15)
    except requests.RequestException as exc:
        st.error(f"Request failed: {exc}")
        return None

    if response.status_code >= 400:
        st.error(f"API error {response.status_code}: {response.text}")
        return None

    if response.text:
        return response.json()
    return None


def format_badge(text: str, color: str) -> str:
    return (
        "<span style=\"background-color:{}; color: white; padding: 2px 8px;"
        " border-radius: 999px; font-size: 0.8em; margin-right: 6px;\">{}</span>"
    ).format(color, text)


def render_queue_card(item: dict, is_selected: bool) -> None:
    badges = [
        format_badge(item.get("topic", "unknown"), "#2563eb"),
        format_badge(item.get("difficulty", "n/a"), "#7c3aed"),
    ]
    risk_flags = item.get("risk_flags") or []
    if risk_flags:
        badges.append(format_badge(", ".join(risk_flags), "#dc2626"))
    confidence = item.get("confidence")
    if confidence is not None:
        badges.append(format_badge(f"conf {confidence}", "#059669"))

    border = "2px solid #2563eb" if is_selected else "1px solid #e5e7eb"
    st.markdown(
        (
            "<div style=\"border:{}; border-radius: 12px; padding: 12px;"
            " margin-bottom: 12px;\">"
            "<div style=\"font-weight: 600; margin-bottom: 6px;\">Request #{}</div>"
            "{}"
            "</div>"
        ).format(border, item.get("id", "?"), " ".join(badges)),
        unsafe_allow_html=True,
    )


def render_detail(item: dict) -> None:
    st.subheader(f"Request #{item.get('id', '?')}")
    st.warning("Review request text carefully for PII before approving.")
    st.markdown("**Request text**")
    st.text_area(
        "request_text",
        value=item.get("request_text", ""),
        height=150,
        key=f"request_text_{item.get('id')}",
        disabled=True,
        label_visibility="collapsed",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Triage JSON**")
        triage = item.get("triage_json", {})
        st.code(json.dumps(triage, ensure_ascii=False, indent=2), language="json")
    with col2:
        st.markdown("**Rationale**")
        st.text_area(
            "rationale",
            value=item.get("rationale", ""),
            height=120,
            key=f"rationale_{item.get('id')}",
            disabled=True,
            label_visibility="collapsed",
        )
        st.markdown("**User reply draft**")
        st.text_area(
            "reply",
            value=item.get("user_reply_draft", ""),
            height=120,
            key=f"reply_{item.get('id')}",
            disabled=True,
            label_visibility="collapsed",
        )


def render_actions(item: dict) -> None:
    st.markdown("---")
    st.subheader("Actions")

    final_handler = st.selectbox("Final handler", FINAL_HANDLERS, key="final_handler")
    note = st.text_area("Admin note", key="admin_note", height=80)

    st.markdown("**Edit before approve**")
    edit_col1, edit_col2 = st.columns(2)
    with edit_col1:
        edited_topic = st.text_input(
            "Topic",
            value=item.get("topic", ""),
            key="edit_topic",
        )
        edited_difficulty = st.text_input(
            "Difficulty",
            value=item.get("difficulty", ""),
            key="edit_difficulty",
        )
    with edit_col2:
        risk_options = sorted(set(KNOWN_RISK_FLAGS + (item.get("risk_flags") or [])))
        edited_risk_flags = st.multiselect(
            "Risk flags",
            options=risk_options,
            default=item.get("risk_flags") or [],
            key="edit_risk_flags",
        )

    action_col1, action_col2, action_col3 = st.columns(3)
    with action_col1:
        if st.button("Approve", use_container_width=True):
            payload = {
                "final_handler": final_handler,
                "note": note,
            }
            response = request_json(
                "POST",
                f"/api/admin/requests/{item.get('id')}/approve",
                payload=payload,
            )
            if response is not None:
                st.session_state.last_approval_summary = response
                st.success("Approved.")

    with action_col2:
        if st.button("Edit + Approve", use_container_width=True):
            payload = {
                "final_handler": final_handler,
                "note": note,
                "topic": edited_topic,
                "difficulty": edited_difficulty,
                "risk_flags": edited_risk_flags,
            }
            response = request_json(
                "POST",
                f"/api/admin/requests/{item.get('id')}/edit_approve",
                payload=payload,
            )
            if response is not None:
                st.session_state.last_approval_summary = response
                st.success("Edited and approved.")

    with action_col3:
        if st.button("Reject", use_container_width=True):
            payload = {"note": note}
            response = request_json(
                "POST",
                f"/api/admin/requests/{item.get('id')}/reject",
                payload=payload,
            )
            if response is not None:
                st.success("Rejected.")


st.title("Admin Review")
st.caption(f"Backend: {BACKEND_URL}")
require_password()

if "selected_request" not in st.session_state:
    st.session_state.selected_request = None

refresh_col, _ = st.columns([1, 4])
with refresh_col:
    if st.button("Refresh queue"):
        st.session_state.queue_data = None

if st.session_state.get("queue_data") is None:
    queue_data = request_json("GET", "/api/admin/queue") or []
    st.session_state.queue_data = queue_data
else:
    queue_data = st.session_state.queue_data

queue_col, detail_col = st.columns([1, 2])

with queue_col:
    st.subheader("Pending queue")
    if not queue_data:
        st.info("No pending requests.")
    for item in queue_data:
        is_selected = st.session_state.selected_request == item.get("id")
        render_queue_card(item, is_selected)
        if st.button(
            "Open",
            key=f"open_{item.get('id')}",
            use_container_width=True,
        ):
            st.session_state.selected_request = item.get("id")

with detail_col:
    selected_id = st.session_state.selected_request
    selected_item = next((i for i in queue_data if i.get("id") == selected_id), None)

    if not selected_item:
        st.info("Select a request from the queue.")
    else:
        detail = request_json(
            "GET",
            f"/api/admin/requests/{selected_item.get('id')}",
        )
        if detail is None:
            st.error("Unable to load details.")
        else:
            render_detail(detail)
            render_actions(detail)

if summary := st.session_state.get("last_approval_summary"):
    st.markdown("---")
    st.subheader("Growthmaru manual registration summary")
    st.json(summary)
    csv_response = None
    if st.button("Download approved CSV"):
        try:
            csv_response = requests.get(
                f"{BACKEND_URL}/api/export/csv",
                timeout=20,
            )
            csv_response.raise_for_status()
        except requests.RequestException as exc:
            st.error(f"CSV download failed: {exc}")

    if csv_response is not None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            "Save CSV",
            data=csv_response.content,
            file_name=f"approved_{timestamp}.csv",
            mime="text/csv",
        )
