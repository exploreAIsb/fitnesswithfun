"""Thin wrapper that runs a Gemini-backed ADK agent for short prompts."""

from __future__ import annotations

import logging
import os
import uuid
from typing import List

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

try:
    from mcp_client_tool import suggest_workout_plan_via_mcp as suggest_workout_plan
    USE_MCP = True
except ImportError:
    from workout_tool import suggest_workout_plan
    USE_MCP = False

LOGGER = logging.getLogger(__name__)
logging.getLogger("google_adk.google.adk.runners").setLevel(logging.ERROR)


class AdkSummarizer:
    """Creates a reusable Runner + Agent pair for quick completions."""

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model or os.getenv("ADK_MODEL", "gemini-2.0-flash")
        self.agent = LlmAgent(
            name="user_profile_agent",
            model=self.model,
            instruction=(
                "You are a concise wellness coach. Given JSON structured user data, "
                "highlight the most relevant traits, fitness focus, and one actionable "
                "tip for the next workout. Keep it under 80 words. "
                "When asked to suggest a workout plan, use the suggest_workout_plan tool "
                "which queries the Kaggle gym exercise dataset (niharika41298/gym-exercise-data) "
                "via MCP server based on the user's age, daily goal, intensity, mood, "
                "injury restrictions, and available exercise time. "
                "Create a personalized workout plan using ONLY exercises from that dataset."
            ),
            tools=[suggest_workout_plan],
        )
        self.app = App(name="wellness_lookup_app", root_agent=self.agent)
        self.session_service = InMemorySessionService()
        self.runner = Runner(app=self.app, session_service=self.session_service)

    def summarize(self, payload: dict) -> str:
        """Generate a friendly summary for the provided user payload."""
        prompt = (
            "Summarize the following user fitness profile and mention a single "
            f"actionable next step:\n{payload}"
        )
        try:
            events = list(
                self.runner.run(
                    user_id="web-user",
                    session_id=self._new_session_id(),
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=prompt)]
                    ),
                )
            )
            return self._last_text_chunk(events) or ""
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Falling back to static summary: %s", exc)
            return "Summary unavailable. Please double-check your Gemini credentials."

    def _new_session_id(self) -> str:
        session = self.session_service.create_session_sync(
            app_name=self.app.name,
            user_id="web-user",
            session_id=str(uuid.uuid4()),
        )
        return session.id

    @staticmethod
    def _last_text_chunk(events: List) -> str:
        for event in reversed(events):
            if not getattr(event, "content", None):
                continue
            parts = getattr(event.content, "parts", None) or []
            texts = [
                part.text
                for part in parts
                if getattr(part, "text", None) and not getattr(part, "thought", False)
            ]
            if texts:
                return "\n".join(texts).strip()
        return ""

    def generate_workout_plan(self, user_data: dict) -> str:
        """Generate a personalized workout plan using the Kaggle exercise dataset via MCP server."""
        mcp_note = " (via MCP server)" if USE_MCP else ""
        prompt = (
            "Based on the following user profile, suggest a personalized workout plan "
            f"using the suggest_workout_plan tool{mcp_note}. Use ONLY exercises from the Kaggle "
            "gym exercise dataset (niharika41298/gym-exercise-data). Consider the user's age, "
            "daily goal, intensity preference, mood, injury restrictions, and available exercise time. "
            "Format the workout plan clearly with exercise names, sets, reps, and duration.\n\n"
            f"User profile: {user_data}"
        )
        try:
            events = list(
                self.runner.run(
                    user_id="web-user",
                    session_id=self._new_session_id(),
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=prompt)]
                    ),
                )
            )
            return self._last_text_chunk(events) or ""
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to generate workout plan: %s", exc)
            return "Workout plan generation unavailable. Please check your configuration."

