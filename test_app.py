"""Tests for app.py – Flask routes, _normalize_payload, and error handler."""

from __future__ import annotations

import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest

# Patch heavy external dependencies before importing app module.
# AdkSummarizer lives in adk_client which imports google.adk (unavailable in CI).
# We inject a fake module so the import chain succeeds without the real SDK.
_fake_adk_client = MagicMock()
_mock_summarizer_instance = MagicMock()
_fake_adk_client.AdkSummarizer.return_value = _mock_summarizer_instance
sys.modules["adk_client"] = _fake_adk_client

with patch("db.upsert_seed_data"):
    import app as app_module

# Point the module-level summarizer to our controllable mock
app_module.adk_summarizer = _mock_summarizer_instance

_VALID_USER_PAYLOAD = {
    "username": "testuser",
    "age": 25,
    "height": 70.0,
    "weight": 160.0,
    "restrictions": "none",
    "goals": "Build muscle",
    "mood": "Energetic",
    "exercise_minutes": 30,
    "intensity": "high",
    "daily_goal": "Push-ups",
}

_STORED_USER = {
    "username": "testuser",
    "age": 25,
    "height": 70.0,
    "weight": 160.0,
    "restrictions": "none",
    "goals": "Build muscle",
    "mood": "Energetic",
    "exercise_minutes": 30,
    "intensity": "high",
    "daily_goal": "Push-ups",
    "created_at": "2026-01-01 00:00:00",
}


@pytest.fixture()
def client():
    """Flask test client with testing mode enabled."""
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_summarizer():
    """Reset the mock summarizer before each test so calls don't leak."""
    app_module.adk_summarizer.reset_mock()
    app_module.adk_summarizer.summarize.return_value = "Great profile!"
    app_module.adk_summarizer.generate_workout_plan.return_value = "Do 3 sets of squats."


# ---------------------------------------------------------------------------
# GET /  (index)
# ---------------------------------------------------------------------------

class TestIndex:
    def test_index_returns_html(self, client):
        # Verify the root route renders the index template and returns 200
        resp = client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        # Health endpoint should always return {"status": "ok"}
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /api/users/lookup
# ---------------------------------------------------------------------------

class TestLookupUser:
    def test_missing_username_returns_400(self, client):
        # Empty username should be rejected with a 400 error
        resp = client.post("/api/users/lookup", json={"username": ""})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Username is required."

    def test_no_username_key_returns_400(self, client):
        # Payload without username key should be rejected
        resp = client.post("/api/users/lookup", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Username is required."

    def test_whitespace_only_username_returns_400(self, client):
        # Whitespace-only username should be treated as empty
        resp = client.post("/api/users/lookup", json={"username": "   "})
        assert resp.status_code == 400

    @patch("app.fetch_user", return_value=None)
    def test_user_not_found(self, mock_fetch, client):
        # Non-existent user should return status "not_found"
        resp = client.post("/api/users/lookup", json={"username": "ghost"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "not_found"
        mock_fetch.assert_called_once_with("ghost")

    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_user_found(self, mock_fetch, client):
        # Existing user should return user data and a summary
        resp = client.post("/api/users/lookup", json={"username": "TestUser"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "found"
        assert body["user"]["username"] == "testuser"
        assert body["summary"] == "Great profile!"
        # Username should be lowercased before lookup
        mock_fetch.assert_called_once_with("testuser")

    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_username_is_lowercased_and_stripped(self, mock_fetch, client):
        # Leading/trailing spaces and mixed case should be normalized
        resp = client.post("/api/users/lookup", json={"username": "  TestUser  "})
        assert resp.status_code == 200
        mock_fetch.assert_called_once_with("testuser")

    def test_null_username_returns_400(self, client):
        # null username should be treated as missing
        resp = client.post("/api/users/lookup", json={"username": None})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/users  (create)
# ---------------------------------------------------------------------------

class TestCreateUser:
    def test_missing_username_returns_400(self, client):
        # Creating a user without a username should fail
        resp = client.post("/api/users", json={"age": 25})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Username is required."

    @patch("app.insert_user", return_value=_STORED_USER)
    def test_successful_creation(self, mock_insert, client):
        # Valid payload should create user and return 201
        resp = client.post("/api/users", json=_VALID_USER_PAYLOAD)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["status"] == "created"
        assert body["user"]["username"] == "testuser"
        assert body["summary"] == "Great profile!"
        mock_insert.assert_called_once()

    @patch("app.insert_user", side_effect=sqlite3.IntegrityError("UNIQUE constraint"))
    def test_duplicate_username_returns_409(self, mock_insert, client):
        # Duplicate username should return 409 conflict
        resp = client.post("/api/users", json=_VALID_USER_PAYLOAD)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "Username already exists."

    @patch("app.insert_user", return_value=None)
    def test_insert_returns_none_uses_validated(self, mock_insert, client):
        # When insert_user returns None, the validated payload is used as fallback
        resp = client.post("/api/users", json=_VALID_USER_PAYLOAD)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["user"]["username"] == "testuser"

    def test_missing_required_fields_returns_400(self, client):
        # Payload missing required numeric fields should trigger ValueError -> 400
        resp = client.post("/api/users", json={"username": "newuser"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert "Missing required fields" in body["error"]

    def test_empty_body_returns_400(self, client):
        # Completely empty body should fail on username check
        resp = client.post("/api/users", json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PUT /api/users/<username>  (update)
# ---------------------------------------------------------------------------

class TestUpdateUser:
    @patch("app.fetch_user", return_value=None)
    def test_user_not_found_returns_404(self, mock_fetch, client):
        # Updating a non-existent user should return 404
        resp = client.put("/api/users/ghost", json=_VALID_USER_PAYLOAD)
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "User not found."

    @patch("app.update_user", return_value=_STORED_USER)
    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_successful_update(self, mock_fetch, mock_update, client):
        # Valid update should return updated user and summary
        resp = client.put("/api/users/testuser", json=_VALID_USER_PAYLOAD)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "updated"
        assert body["user"]["username"] == "testuser"
        assert body["summary"] == "Great profile!"

    @patch("app.update_user", side_effect=RuntimeError("DB write failed"))
    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_update_exception_returns_500(self, mock_fetch, mock_update, client):
        # Database failure during update should return 500
        resp = client.put("/api/users/testuser", json=_VALID_USER_PAYLOAD)
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Unable to update user."

    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_update_missing_required_fields_returns_400(self, mock_fetch, client):
        # Update with missing required fields triggers ValueError -> 400
        resp = client.put("/api/users/testuser", json={"goals": "Run faster"})
        assert resp.status_code == 400
        assert "Missing required fields" in resp.get_json()["error"]

    @patch("app.update_user", return_value=_STORED_USER)
    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_username_in_url_is_normalized(self, mock_fetch, mock_update, client):
        # URL username should be lowercased and stripped
        resp = client.put("/api/users/TestUser", json=_VALID_USER_PAYLOAD)
        assert resp.status_code == 200
        mock_fetch.assert_called_once_with("testuser")


# ---------------------------------------------------------------------------
# POST /api/workout-plan
# ---------------------------------------------------------------------------

class TestGenerateWorkoutPlan:
    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_workout_plan_with_username(self, mock_fetch, client):
        # Providing a username should look up the user and generate a plan
        resp = client.post("/api/workout-plan", json={"username": "testuser"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["workout_plan"] == "Do 3 sets of squats."
        assert body["user"]["username"] == "testuser"
        assert body["is_follow_up"] is False

    @patch("app.fetch_user", return_value=None)
    def test_workout_plan_user_not_found(self, mock_fetch, client):
        # Non-existent username should return 404
        resp = client.post("/api/workout-plan", json={"username": "ghost"})
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "User not found."

    def test_workout_plan_without_username_uses_payload(self, client):
        # No username means the raw payload is used as user_data
        payload = {"age": 30, "weight": 150, "height": 65}
        resp = client.post("/api/workout-plan", json=payload)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["user"] == payload

    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_workout_plan_follow_up(self, mock_fetch, client):
        # Follow-up request should pass is_follow_up=True and additional_requirements
        payload = {
            "username": "testuser",
            "is_follow_up": True,
            "additional_requirements": "Add more cardio",
        }
        resp = client.post("/api/workout-plan", json=payload)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["is_follow_up"] is True
        app_module.adk_summarizer.generate_workout_plan.assert_called_once_with(
            _STORED_USER,
            additional_requirements="Add more cardio",
            is_follow_up=True,
        )

    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_workout_plan_exception_returns_500(self, mock_fetch, client):
        # Exception during plan generation should return 500
        app_module.adk_summarizer.generate_workout_plan.side_effect = RuntimeError("LLM down")
        resp = client.post("/api/workout-plan", json={"username": "testuser"})
        assert resp.status_code == 500
        assert "Unable to generate workout plan" in resp.get_json()["error"]

    def test_workout_plan_empty_body(self, client):
        # Empty body should use payload directly (no username)
        resp = client.post("/api/workout-plan", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"

    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_workout_plan_empty_additional_requirements(self, mock_fetch, client):
        # Empty additional_requirements string should be treated as None
        payload = {"username": "testuser", "additional_requirements": "   "}
        resp = client.post("/api/workout-plan", json=payload)
        assert resp.status_code == 200
        app_module.adk_summarizer.generate_workout_plan.assert_called_once_with(
            _STORED_USER,
            additional_requirements=None,
            is_follow_up=False,
        )


# ---------------------------------------------------------------------------
# _normalize_payload
# ---------------------------------------------------------------------------

class TestNormalizePayload:
    def test_valid_payload(self):
        # All required fields present should return a well-typed dict
        result = app_module._normalize_payload("alice", _VALID_USER_PAYLOAD)
        assert result["username"] == "alice"
        assert result["age"] == 25
        assert isinstance(result["height"], float)
        assert isinstance(result["weight"], float)
        assert result["exercise_minutes"] == 30
        assert result["intensity"] == "high"

    def test_missing_required_fields_raises(self):
        # Omitting required numeric fields should raise ValueError
        with pytest.raises(ValueError, match="Missing required fields"):
            app_module._normalize_payload("bob", {})

    def test_partial_missing_fields(self):
        # Only some required fields present should list the missing ones
        raw = {"age": 30, "height": 70}
        with pytest.raises(ValueError, match="weight"):
            app_module._normalize_payload("bob", raw)

    def test_non_numeric_age_returns_none_and_raises(self):
        # Non-numeric age should be cast to None, triggering missing field error
        raw = {**_VALID_USER_PAYLOAD, "age": "not-a-number"}
        with pytest.raises(ValueError, match="age"):
            app_module._normalize_payload("bob", raw)

    def test_empty_string_values_treated_as_missing(self):
        # Empty string for numeric fields should be treated as None -> missing
        raw = {**_VALID_USER_PAYLOAD, "weight": ""}
        with pytest.raises(ValueError, match="weight"):
            app_module._normalize_payload("bob", raw)

    def test_none_values_treated_as_missing(self):
        # None for required numeric fields should be treated as missing
        raw = {**_VALID_USER_PAYLOAD, "exercise_minutes": None}
        with pytest.raises(ValueError, match="exercise_minutes"):
            app_module._normalize_payload("bob", raw)

    def test_exercise_time_fallback(self):
        # exercise_time should be used when exercise_minutes is absent
        raw = {
            "age": 25, "height": 70, "weight": 160,
            "exercise_time": 45, "intensity": "low",
        }
        result = app_module._normalize_payload("carol", raw)
        assert result["exercise_minutes"] == 45

    def test_daily_goal_fallback(self):
        # dailyGoal (camelCase) should be used when daily_goal is absent
        raw = {
            "age": 25, "height": 70, "weight": 160,
            "exercise_minutes": 30, "intensity": "moderate",
            "dailyGoal": "Run 5k",
        }
        result = app_module._normalize_payload("dave", raw)
        assert result["daily_goal"] == "Run 5k"

    def test_strings_are_stripped(self):
        # String fields should have leading/trailing whitespace removed
        raw = {
            **_VALID_USER_PAYLOAD,
            "restrictions": "  bad knee  ",
            "goals": "  lose weight  ",
            "mood": "  tired  ",
            "intensity": "  moderate  ",
            "daily_goal": "  run  ",
        }
        result = app_module._normalize_payload("eve", raw)
        assert result["restrictions"] == "bad knee"
        assert result["goals"] == "lose weight"
        assert result["mood"] == "tired"
        assert result["intensity"] == "moderate"
        assert result["daily_goal"] == "run"

    def test_none_string_fields_become_empty(self):
        # None for optional string fields should become empty string
        raw = {
            "age": 25, "height": 70, "weight": 160,
            "exercise_minutes": 30, "intensity": "high",
            "restrictions": None, "goals": None, "mood": None,
        }
        result = app_module._normalize_payload("frank", raw)
        assert result["restrictions"] == ""
        assert result["goals"] == ""
        assert result["mood"] == ""

    def test_float_height_and_weight(self):
        # String representations of floats should be properly cast
        raw = {
            "age": "25", "height": "70.5", "weight": "160.3",
            "exercise_minutes": "30", "intensity": "high",
        }
        result = app_module._normalize_payload("grace", raw)
        assert result["age"] == 25
        assert result["height"] == 70.5
        assert result["weight"] == 160.3
        assert result["exercise_minutes"] == 30


# ---------------------------------------------------------------------------
# ValueError error handler
# ---------------------------------------------------------------------------

class TestValueErrorHandler:
    def test_value_error_returns_400(self, client):
        # _normalize_payload raising ValueError should be caught by the handler
        payload = {"username": "newuser"}
        resp = client.post("/api/users", json=payload)
        assert resp.status_code == 400
        assert "Missing required fields" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# Adversarial / edge cases
# ---------------------------------------------------------------------------

class TestAdversarial:
    @patch("app.fetch_user", return_value=None)
    def test_lookup_with_unicode_username(self, mock_fetch, client):
        # Unicode characters in username should not crash the app
        resp = client.post("/api/users/lookup", json={"username": "用户名"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "not_found"

    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_lookup_with_very_long_username(self, mock_fetch, client):
        # Extremely long username should be handled gracefully
        long_name = "a" * 10000
        resp = client.post("/api/users/lookup", json={"username": long_name})
        assert resp.status_code == 200

    def test_create_user_with_negative_age(self, client):
        # Negative age should still be accepted by _normalize_payload (no validation)
        raw = {**_VALID_USER_PAYLOAD, "username": "neg", "age": -5}
        with patch("app.insert_user", return_value=None):
            resp = client.post("/api/users", json=raw)
        assert resp.status_code == 201
        assert resp.get_json()["user"]["age"] == -5

    def test_create_user_with_zero_weight(self, client):
        # Zero weight should be accepted (no business validation on range)
        raw = {**_VALID_USER_PAYLOAD, "username": "zero", "weight": 0}
        with patch("app.insert_user", return_value=None):
            resp = client.post("/api/users", json=raw)
        assert resp.status_code == 201
        assert resp.get_json()["user"]["weight"] == 0.0

    def test_create_user_with_special_chars_in_strings(self, client):
        # Special characters and HTML in string fields should pass through
        raw = {
            **_VALID_USER_PAYLOAD,
            "username": "xss",
            "goals": '<script>alert("xss")</script>',
            "restrictions": "'; DROP TABLE users; --",
        }
        with patch("app.insert_user", return_value=None):
            resp = client.post("/api/users", json=raw)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["user"]["goals"] == '<script>alert("xss")</script>'
        assert body["user"]["restrictions"] == "'; DROP TABLE users; --"

    def test_workout_plan_with_xss_in_requirements(self, client):
        # XSS in additional_requirements should not crash the endpoint
        payload = {
            "additional_requirements": '<img src=x onerror=alert(1)>',
        }
        resp = client.post("/api/workout-plan", json=payload)
        assert resp.status_code == 200

    @patch("app.fetch_user", return_value=_STORED_USER)
    def test_workout_plan_additional_requirements_none(self, mock_fetch, client):
        # Explicit None for additional_requirements should be handled
        payload = {"username": "testuser", "additional_requirements": None}
        resp = client.post("/api/workout-plan", json=payload)
        assert resp.status_code == 200
        app_module.adk_summarizer.generate_workout_plan.assert_called_once_with(
            _STORED_USER,
            additional_requirements=None,
            is_follow_up=False,
        )

    def test_non_json_body_lookup(self, client):
        # Non-JSON body with force=True should be parsed or default to {}
        resp = client.post(
            "/api/users/lookup",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_create_user_boolean_age(self, client):
        # Boolean True is int-castable (True -> 1), so it should not crash
        raw = {**_VALID_USER_PAYLOAD, "username": "booluser", "age": True}
        with patch("app.insert_user", return_value=None):
            resp = client.post("/api/users", json=raw)
        assert resp.status_code == 201
        assert resp.get_json()["user"]["age"] == 1

    def test_create_user_list_as_age_raises(self, client):
        # A list for age should fail type casting -> missing field -> 400
        raw = {**_VALID_USER_PAYLOAD, "username": "listuser", "age": [1, 2]}
        resp = client.post("/api/users", json=raw)
        assert resp.status_code == 400
