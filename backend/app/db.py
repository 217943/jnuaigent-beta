import os
import sqlite3
from pathlib import Path
from typing import Generator

DB_ENV_KEY = "TRIAGE_DB_PATH"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "triage.db"


def get_db_path() -> Path:
    return Path(os.getenv(DB_ENV_KEY, DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    connection = get_connection()
    with connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                user_role TEXT,
                modality_pref TEXT,
                request_text TEXT NOT NULL,
                tools_hint TEXT,
                status TEXT NOT NULL,
                triage_json TEXT NOT NULL,
                triage_confidence REAL NOT NULL,
                risk_flags_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                action TEXT NOT NULL,
                final_topic TEXT,
                final_difficulty TEXT,
                final_handler TEXT,
                note TEXT,
                FOREIGN KEY(request_id) REFERENCES requests(id)
            )
            """
        )
    connection.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
