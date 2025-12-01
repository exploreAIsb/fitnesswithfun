from __future__ import annotations

import logging
import os
from typing import Any, Dict

import sqlite3
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from adk_client import AdkSummarizer
from db import fetch_user, insert_user, update_user, upsert_seed_data

load_dotenv()

# Configure logging to both file and console
log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE", "app.log")

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)
log_path = os.path.join("logs", log_file)

# Configure root logger
logging.basicConfig(
    level=getattr(logging, log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()  # Also log to console
    ]
)

LOGGER = logging.getLogger(__name__)
LOGGER.info(f"Logging initialized. Log file: {log_path}")

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


@app.route("/api/users/<username>", methods=["PUT"])
def update_user_profile(username: str):
    """Update an existing user's profile."""
    username = username.strip().lower()
    if not username:
        return jsonify({"error": "Username is required."}), 400

    # Check if user exists
    existing = fetch_user(username)
    if not existing:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json(force=True) or {}
    validated = _normalize_payload(username, data)
    
    try:
        updated = update_user(username, validated)
        summary = adk_summarizer.summarize(updated)
        return jsonify({"status": "updated", "user": updated, "summary": summary})
    except Exception as exc:
        LOGGER.exception("Failed to update user: %s", exc)
        return jsonify({"error": "Unable to update user."}), 500


@app.route("/api/workout-plan", methods=["POST"])
def generate_workout_plan():
    """
    Generate or refine a personalized workout plan using the Kaggle exercise dataset.
    
    Supports ADK session memory for conversational refinement:
    - Initial request: generates workout plan based on user profile
    - Follow-up requests: refines plan with additional requirements using session memory
    """
    payload = request.get_json(force=True) or {}
    LOGGER.info(f"Workout plan request received: {payload}")
    
    username = (payload.get("username") or "").strip().lower()
    additional_requirements = payload.get("additional_requirements", "").strip()
    is_follow_up = payload.get("is_follow_up", False)
    
    LOGGER.info(f"Processing workout plan - username: {username}, is_follow_up: {is_follow_up}, additional_requirements: {additional_requirements[:50] if additional_requirements else 'None'}...")
    
    if username:
        # Get user from database
        user_data = fetch_user(username)
        if not user_data:
            LOGGER.warning(f"User not found: {username}")
            return jsonify({"error": "User not found."}), 404
        LOGGER.info(f"User data retrieved: {username}")
    else:
        # Use provided user data directly
        user_data = payload
        LOGGER.info("Using provided user data directly")
    
    try:
        LOGGER.info(f"Calling adk_summarizer.generate_workout_plan for user: {user_data.get('username', 'unknown')}")
        workout_plan = adk_summarizer.generate_workout_plan(
            user_data,
            additional_requirements=additional_requirements if additional_requirements else None,
            is_follow_up=is_follow_up
        )
        LOGGER.info(f"Workout plan generated successfully. Length: {len(workout_plan) if workout_plan else 0} characters")
        if workout_plan:
            LOGGER.debug(f"Workout plan preview: {workout_plan[:200]}...")
        else:
            LOGGER.warning("Workout plan is empty!")
        
        return jsonify({
            "status": "success",
            "workout_plan": workout_plan,
            "user": user_data,
            "is_follow_up": is_follow_up
        })
    except Exception as exc:
        LOGGER.exception("Failed to generate workout plan: %s", exc)
        return jsonify({"error": f"Unable to generate workout plan: {str(exc)}"}), 500


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
    port = int(os.getenv("PORT", 5001))
    app.run(debug=True, port=port)

