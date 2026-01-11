# AGENTS

## Project goal
Build the initial scaffold for the "AI Clinic Triage MVP" in a university setting. The MVP focuses on classifying inquiries and preparing structured outputs for manual registration/export.

## Safety constraints
- Do **not** provide medical, legal, or psychological advice. Only classify and route.
- Do **not** include any file upload functionality.
- Do **not** integrate Growthmaru or any external registration systems.
- Avoid collecting sensitive personal data beyond what is required for triage.

## Core flows
1. User submits a free-text description of their situation.
2. The triage agent classifies the case (role, issue type, urgency, risk flags).
3. The system outputs a structured JSON payload for manual registration/export.

## Done criteria
- Root-level folders exist: `prompts/`, `schemas/`, `data/`, `backend/`, `admin/`.
- `prompts/triage_system.txt` contains a Korean system prompt focused on classification only.
- `schemas/triage_output.schema.json` defines the output schema used by the triage agent.
- `data/fewshot_examples.jsonl` contains 6 examples that match the schema.
- `README.md` documents how to run the FastAPI backend and Streamlit admin, and includes Korean text.
