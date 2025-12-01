"""Lightweight SQLite helpers for the ADK demo app."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "instance" / "users.db"


def database_path() -> Path:
    """Return the configured database path, ensuring its parent exists."""
    configured = os.getenv("DATABASE_PATH")
    path = Path(configured).expanduser() if configured else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection with row access by column name."""
    conn = sqlite3.connect(database_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db(sample_users: Optional[Iterable[Dict[str, Any]]] = None, *, drop_existing: bool = False) -> None:
    """Create tables and seed optional data."""
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        age INTEGER,
        height REAL,
        weight REAL,
        restrictions TEXT,
        goals TEXT,
        mood TEXT,
        exercise_minutes INTEGER,
        intensity TEXT,
        daily_goal TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
    with get_connection() as conn:
        cur = conn.cursor()
        if drop_existing:
            cur.execute("DROP TABLE IF EXISTS users;")
        cur.executescript(schema)
        if sample_users:
            cur.executemany(
                """
                INSERT OR REPLACE INTO users (
                    username, age, height, weight, restrictions, goals,
                    mood, exercise_minutes, intensity, daily_goal
                ) VALUES (
                    :username, :age, :height, :weight, :restrictions, :goals,
                    :mood, :exercise_minutes, :intensity, :daily_goal
                );
                """,
                list(sample_users),
            )
        conn.commit()


def fetch_user(username: str) -> Optional[Dict[str, Any]]:
    """Return a user dict or None."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def insert_user(user_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Insert and return the stored user."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                username, age, height, weight, restrictions, goals, mood,
                exercise_minutes, intensity, daily_goal
            ) VALUES (
                :username, :age, :height, :weight, :restrictions, :goals, :mood,
                :exercise_minutes, :intensity, :daily_goal
            );
            """,
            user_payload,
        )
        conn.commit()
    stored = fetch_user(user_payload["username"])
    if not stored:  # pragma: no cover - defensive
        raise RuntimeError("Failed to read the stored user record.")
    return stored


def upsert_seed_data() -> None:
    """Create the database with minimal demo users if it is empty."""
    init_db()
    if fetch_user("alex") or fetch_user("jordan"):
        return
    init_db(
        sample_users=[
            {
                "username": "alex",
                "age": 32,
                "height": 68,
                "weight": 159,
                "restrictions": "knee injury",
                "goals": "Build lean muscle",
                "mood": "Focused",
                "exercise_minutes": 45,
                "intensity": "moderate",
                "daily_goal": "Add 20 push-ups",
            },
            {
                "username": "jordan",
                "age": 41,
                "height": 71,
                "weight": 185,
                "restrictions": "none",
                "goals": "Marathon prep",
                "mood": "Motivated",
                "exercise_minutes": 60,
                "intensity": "high",
                "daily_goal": "Negative split tempo run",
            },
        ]
    )

