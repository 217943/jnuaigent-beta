# AI Clinic Triage MVP (University)

이 프로젝트는 대학 환경의 상담/의료 관련 문의를 **분류(triage)** 하기 위한 최소 기능 제품(MVP)입니다. 해결책 제공이 아닌 분류와 라우팅에 집중합니다.

## Scope
- **Manual registration/export only** (no Growthmaru integration).
- **No file upload** in the MVP.

## Repository structure
- `prompts/` – system prompts for the triage agent
- `schemas/` – JSON schema for structured outputs
- `data/` – few-shot examples used for prompt or evaluation
- `backend/` – FastAPI service (scaffold)
- `admin/` – Streamlit admin app (scaffold)

## Backend (FastAPI)
FastAPI 백엔드를 실행하는 방법입니다:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Admin (Streamlit)
Streamlit 관리자 UI를 실행하는 방법입니다:
```bash
cd admin
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run admin_app.py
```

## Notes
- Output is intended for **manual registration/export**.
- No Growthmaru integration in MVP.
- No file uploads anywhere in MVP.
