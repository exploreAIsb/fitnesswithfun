from __future__ import annotations

import logging
import os
from typing import Any, Dict

import sqlite3
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from adk_client import AdkSummarizer
from db import fetch_user, insert_user, upsert_seed_data

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger(__name__)

app = Flask(__name__)
adk_summarizer = AdkSummarizer()

# Make sure the database exists with a couple of demo users.
upsert_seed_data()


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/users/lookup", methods=["POST"])
def lookup_user():
    payload = request.get_json(force=True) or {}
    username = (payload.get("username") or "").strip().lower()
    if not username:
        return jsonify({"error": "Username is required."}), 400

    record = fetch_user(username)
    if not record:
        return jsonify({"status": "not_found"})

    summary = adk_summarizer.summarize(record)
    return jsonify({"status": "found", "user": record, "summary": summary})


@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    if not username:
        return jsonify({"error": "Username is required."}), 400

    validated = _normalize_payload(username, data)
    try:
        stored = insert_user(validated)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists."}), 409
    except Exception as exc:  # pragma: no cover - sqlite constraint failure
        LOGGER.exception("Failed to insert user: %s", exc)
        return jsonify({"error": "Unable to save user."}), 500

    stored = stored or validated
    summary = adk_summarizer.summarize(stored)
    return jsonify({"status": "created", "user": stored, "summary": summary}), 201


@app.route("/api/workout-plan", methods=["POST"])
def generate_workout_plan():
    """Generate a personalized workout plan using the Kaggle exercise dataset."""
    payload = request.get_json(force=True) or {}
    username = (payload.get("username") or "").strip().lower()
    
    if username:
        # Get user from database
        user_data = fetch_user(username)
        if not user_data:
            return jsonify({"error": "User not found."}), 404
    else:
        # Use provided user data directly
        user_data = payload
    
    try:
        workout_plan = adk_summarizer.generate_workout_plan(user_data)
        return jsonify({
            "status": "success",
            "workout_plan": workout_plan,
            "user": user_data
        })
    except Exception as exc:
        LOGGER.exception("Failed to generate workout plan: %s", exc)
        return jsonify({"error": "Unable to generate workout plan."}), 500


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


def _normalize_payload(username: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Cast incoming JSON payload to the types expected by SQLite."""
    def _num(value: Any, cast_type):
        try:
            return cast_type(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    mapped: Dict[str, Any] = {
        "username": username,
        "age": _num(raw.get("age"), int),
        "height": _num(raw.get("height"), float),
        "weight": _num(raw.get("weight"), float),
        "restrictions": (raw.get("restrictions") or "").strip(),
        "goals": (raw.get("goals") or "").strip(),
        "mood": (raw.get("mood") or "").strip(),
        "exercise_minutes": _num(raw.get("exercise_minutes") or raw.get("exercise_time"), int),
        "intensity": (raw.get("intensity") or "").strip(),
        "daily_goal": (raw.get("daily_goal") or raw.get("dailyGoal") or "").strip(),
    }
    missing = [
        field
        for field in ("age", "height", "weight", "exercise_minutes", "intensity")
        if mapped[field] in (None, "")
    ]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    return mapped


@app.errorhandler(ValueError)
def handle_value_error(err: ValueError):
    return jsonify({"error": str(err)}), 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)

