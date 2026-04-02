from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

with patch("adk_client.LlmAgent"), \
     patch("adk_client.App"), \
     patch("adk_client.InMemorySessionService"), \
     patch("adk_client.Runner"), \
     patch("adk_client.suggest_workout_plan"), \
     patch("db.upsert_seed_data"):
    from app import _normalize_payload, app


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def mock_adk(monkeypatch):
    summarizer = MagicMock()
    summarizer.summarize.return_value = "Great profile!"
    summarizer.generate_workout_plan.return_value = "Do 3 sets of squats."
    monkeypatch.setattr("app.adk_summarizer", summarizer)
    return summarizer


VALID_USER_PAYLOAD: Dict[str, Any] = {
    "username": "testuser",
    "age": 25,
    "height": 70.0,
    "weight": 160.0,
    "restrictions": "none",
    "goals": "Build muscle",
    "mood": "Energetic",
    "exercise_minutes": 30,
    "intensity": "high",
    "daily_goal": "Push day",
}


# -- _normalize_payload unit tests --


def test_normalize_payload_valid():
    # Verifies that a fully-populated payload is normalized correctly
    result = _normalize_payload("alice", VALID_USER_PAYLOAD)
    assert result["username"] == "alice"
    assert result["age"] == 25
    assert result["height"] == 70.0
    assert result["weight"] == 160.0
    assert result["exercise_minutes"] == 30
    assert result["intensity"] == "high"
    assert result["daily_goal"] == "Push day"


def test_normalize_payload_strips_whitespace():
    # Whitespace in string fields should be stripped
    raw = {**VALID_USER_PAYLOAD, "goals": "  lose fat  ", "mood": " happy "}
    result = _normalize_payload("bob", raw)
    assert result["goals"] == "lose fat"
    assert result["mood"] == "happy"


def test_normalize_payload_missing_required_field_raises():
    # Missing a required numeric field should raise ValueError listing the field
    raw = {**VALID_USER_PAYLOAD}
    del raw["age"]
    with pytest.raises(ValueError, match="age"):
        _normalize_payload("charlie", raw)


def test_normalize_payload_multiple_missing_fields():
    # All missing required fields should appear in the error message
    raw = {"username": "x"}
    with pytest.raises(ValueError, match="age") as exc_info:
        _normalize_payload("x", raw)
    msg = str(exc_info.value)
    for field in ("age", "height", "weight", "exercise_minutes", "intensity"):
        assert field in msg


def test_normalize_payload_exercise_time_alias():
    # exercise_time should be accepted as an alias for exercise_minutes
    raw = {**VALID_USER_PAYLOAD}
    del raw["exercise_minutes"]
    raw["exercise_time"] = 45
    result = _normalize_payload("dave", raw)
    assert result["exercise_minutes"] == 45


def test_normalize_payload_daily_goal_alias():
    # dailyGoal (camelCase) should be accepted as an alias for daily_goal
    raw = {**VALID_USER_PAYLOAD}
    del raw["daily_goal"]
    raw["dailyGoal"] = "Leg day"
    result = _normalize_payload("eve", raw)
    assert result["daily_goal"] == "Leg day"


def test_normalize_payload_bad_numeric_value():
    # Non-numeric strings for numeric fields should be treated as None → missing
    raw = {**VALID_USER_PAYLOAD, "age": "not-a-number"}
    with pytest.raises(ValueError, match="age"):
        _normalize_payload("frank", raw)


def test_normalize_payload_empty_string_intensity():
    # Empty string for a required field should be treated as missing
    raw = {**VALID_USER_PAYLOAD, "intensity": ""}
    with pytest.raises(ValueError, match="intensity"):
        _normalize_payload("grace", raw)


def test_normalize_payload_none_restrictions():
    # None restrictions should become empty string, not raise
    raw = {**VALID_USER_PAYLOAD, "restrictions": None}
    result = _normalize_payload("hank", raw)
    assert result["restrictions"] == ""


# -- Health endpoint --


def test_health_endpoint(client):
    # Health check should always return 200 with status ok
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


# -- Index route --


def test_index_returns_html(client):
    # Root route should return 200 (renders template)
    with patch("app.render_template", return_value="<html></html>"):
        resp = client.get("/")
        assert resp.status_code == 200


# -- Lookup user --


def test_lookup_user_missing_username(client):
    # Lookup without username should return 400
    resp = client.post("/api/users/lookup", json={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_lookup_user_not_found(client):
    # Lookup for a non-existent user should return not_found status
    with patch("app.fetch_user", return_value=None):
        resp = client.post("/api/users/lookup", json={"username": "ghost"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "not_found"


def test_lookup_user_found(client, mock_adk):
    # Lookup for an existing user should return found status with user data and summary
    user_record = {"username": "alex", "age": 32}
    with patch("app.fetch_user", return_value=user_record):
        resp = client.post("/api/users/lookup", json={"username": "Alex"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "found"
        assert data["user"] == user_record
        assert data["summary"] == "Great profile!"


def test_lookup_user_whitespace_username(client):
    # Username with only whitespace should be treated as empty → 400
    resp = client.post("/api/users/lookup", json={"username": "   "})
    assert resp.status_code == 400


# -- Create user --


def test_create_user_missing_username(client):
    # Create without username should return 400
    resp = client.post("/api/users", json={"age": 25})
    assert resp.status_code == 400


def test_create_user_missing_required_fields(client):
    # Create with username but missing required profile fields should return 400
    resp = client.post("/api/users", json={"username": "newbie"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_create_user_success(client, mock_adk):
    # Successful user creation should return 201 with created status
    stored = {**VALID_USER_PAYLOAD, "username": "testuser"}
    with patch("app.insert_user", return_value=stored):
        resp = client.post("/api/users", json=VALID_USER_PAYLOAD)
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["status"] == "created"
        assert data["user"]["username"] == "testuser"
        assert data["summary"] == "Great profile!"


def test_create_user_duplicate(client, mock_adk):
    # Inserting a duplicate username should return 409
    with patch("app.insert_user", side_effect=sqlite3.IntegrityError):
        resp = client.post("/api/users", json=VALID_USER_PAYLOAD)
        assert resp.status_code == 409
        assert "already exists" in resp.get_json()["error"]


def test_create_user_insert_returns_none_uses_validated(client, mock_adk):
    # When insert_user returns None, the validated payload should be used
    with patch("app.insert_user", return_value=None):
        resp = client.post("/api/users", json=VALID_USER_PAYLOAD)
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["user"]["username"] == "testuser"


# -- Update user --


def test_update_user_not_found(client):
    # Updating a non-existent user should return 404
    with patch("app.fetch_user", return_value=None):
        resp = client.put("/api/users/ghost", json=VALID_USER_PAYLOAD)
        assert resp.status_code == 404


def test_update_user_success(client, mock_adk):
    # Successful update should return 200 with updated status
    existing = {**VALID_USER_PAYLOAD, "username": "testuser"}
    updated = {**existing, "age": 30}
    with patch("app.fetch_user", return_value=existing), \
         patch("app.update_user", return_value=updated):
        resp = client.put(
            "/api/users/testuser",
            json={**VALID_USER_PAYLOAD, "age": 30},
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "updated"
        assert data["user"]["age"] == 30


def test_update_user_db_error(client, mock_adk):
    # Database error during update should return 500
    existing = {**VALID_USER_PAYLOAD, "username": "testuser"}
    with patch("app.fetch_user", return_value=existing), \
         patch("app.update_user", side_effect=RuntimeError("db crash")):
        resp = client.put("/api/users/testuser", json=VALID_USER_PAYLOAD)
        assert resp.status_code == 500
        assert "Unable to update" in resp.get_json()["error"]


# -- Workout plan --


def test_workout_plan_user_not_found(client, mock_adk):
    # Requesting a workout plan for a non-existent user should return 404
    with patch("app.fetch_user", return_value=None):
        resp = client.post("/api/workout-plan", json={"username": "ghost"})
        assert resp.status_code == 404


def test_workout_plan_success_with_username(client, mock_adk):
    # Workout plan for an existing user should return success with plan text
    user = {**VALID_USER_PAYLOAD, "username": "alex"}
    with patch("app.fetch_user", return_value=user):
        resp = client.post("/api/workout-plan", json={"username": "alex"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["workout_plan"] == "Do 3 sets of squats."
        assert data["is_follow_up"] is False


def test_workout_plan_with_inline_data(client, mock_adk):
    # When no username is provided, the payload itself is used as user data
    resp = client.post("/api/workout-plan", json={"age": 25, "intensity": "low"})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "success"


def test_workout_plan_follow_up(client, mock_adk):
    # Follow-up requests should pass is_follow_up=True and additional_requirements
    user = {**VALID_USER_PAYLOAD, "username": "alex"}
    with patch("app.fetch_user", return_value=user):
        resp = client.post("/api/workout-plan", json={
            "username": "alex",
            "is_follow_up": True,
            "additional_requirements": "more cardio",
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["is_follow_up"] is True
        mock_adk.generate_workout_plan.assert_called_once_with(
            user,
            additional_requirements="more cardio",
            is_follow_up=True,
        )


def test_workout_plan_generation_error(client, mock_adk):
    # Exception during plan generation should return 500
    mock_adk.generate_workout_plan.side_effect = RuntimeError("model down")
    user = {**VALID_USER_PAYLOAD, "username": "alex"}
    with patch("app.fetch_user", return_value=user):
        resp = client.post("/api/workout-plan", json={"username": "alex"})
        assert resp.status_code == 500
        assert "Unable to generate" in resp.get_json()["error"]


# -- Adversarial / edge cases --


def test_lookup_user_null_json_body(client):
    # Sending non-JSON content should still be handled gracefully (force=True)
    resp = client.post(
        "/api/users/lookup",
        data="not json",
        content_type="text/plain",
    )
    assert resp.status_code == 400


def test_create_user_unicode_username(client, mock_adk):
    # Unicode characters in username should be accepted
    payload = {**VALID_USER_PAYLOAD, "username": "ユーザー"}
    stored = {**payload, "username": "ユーザー"}
    with patch("app.insert_user", return_value=stored):
        resp = client.post("/api/users", json=payload)
        assert resp.status_code == 201
        assert resp.get_json()["user"]["username"] == "ユーザー"


def test_normalize_payload_zero_age():
    # Zero is a valid number but unusual; should not raise
    raw = {**VALID_USER_PAYLOAD, "age": 0}
    result = _normalize_payload("zero", raw)
    assert result["age"] == 0


def test_normalize_payload_negative_weight():
    # Negative weight is technically parseable; _normalize_payload does not validate ranges
    raw = {**VALID_USER_PAYLOAD, "weight": -100}
    result = _normalize_payload("neg", raw)
    assert result["weight"] == -100.0


def test_normalize_payload_very_large_exercise_minutes():
    # Very large values should be accepted without error
    raw = {**VALID_USER_PAYLOAD, "exercise_minutes": 999999}
    result = _normalize_payload("big", raw)
    assert result["exercise_minutes"] == 999999
