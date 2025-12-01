"""Thin wrapper that runs a Gemini-backed ADK agent for short prompts."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Dict, List, Optional

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

# Configure file logging for adk_client if not already configured
if not LOGGER.handlers:
    import os
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler("logs/adk_client.log")
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    LOGGER.addHandler(file_handler)
    LOGGER.setLevel(logging.INFO)


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
                "Create a personalized workout plan using ONLY exercises from that dataset. "
                "When users provide additional requirements or want to refine the workout plan, "
                "remember the previous context and incorporate the new requirements into an "
                "updated workout plan. Build upon the previous plan rather than starting from scratch."
            ),
            tools=[suggest_workout_plan],
        )
        self.app = App(name="wellness_lookup_app", root_agent=self.agent)
        self.session_service = InMemorySessionService()
        self.runner = Runner(app=self.app, session_service=self.session_service)
        # Store workout plan sessions per user (username -> session_id)
        self._workout_sessions: Dict[str, str] = {}

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

    def _get_workout_session_id(self, username: str, is_follow_up: bool = False) -> str:
        """Get or create a workout plan session for a user."""
        # For follow-ups, reuse the session. For initial requests, create new session.
        # This ensures session memory works for refinements but avoids issues with stale sessions
        if not is_follow_up or username not in self._workout_sessions:
            session_id = self._new_session_id()
            self._workout_sessions[username] = session_id
            LOGGER.info(f"Created new workout session for {username}: {session_id}")
        else:
            LOGGER.info(f"Reusing workout session for {username}: {self._workout_sessions[username]}")
        return self._workout_sessions[username]

    def generate_workout_plan(
        self, 
        user_data: dict, 
        additional_requirements: Optional[str] = None,
        is_follow_up: bool = False
    ) -> str:
        """
        Generate or refine a personalized workout plan using the Kaggle exercise dataset via MCP server.
        
        Uses ADK session memory to maintain context across multiple requests for the same user.
        
        Args:
            user_data: User profile data
            additional_requirements: Optional additional requirements or refinements
            is_follow_up: Whether this is a follow-up request (refining existing plan)
        """
        username = user_data.get("username", "anonymous")
        LOGGER.info(f"Generating workout plan - username: {username}, is_follow_up: {is_follow_up}, has_additional_requirements: {bool(additional_requirements)}")
        
        session_id = self._get_workout_session_id(username, is_follow_up=is_follow_up)
        LOGGER.info(f"Using session_id: {session_id} for user: {username}")
        
        mcp_note = " (via MCP server)" if USE_MCP else ""
        
        if is_follow_up and additional_requirements:
            # Follow-up message: refine existing plan with new requirements
            prompt = (
                f"The user wants to refine their workout plan with the following additional requirements: "
                f"{additional_requirements}\n\n"
                "Please update the workout plan using the suggest_workout_plan tool, incorporating "
                "these new requirements while maintaining consistency with the previous plan. "
                "Use ONLY exercises from the Kaggle gym exercise dataset (niharika41298/gym-exercise-data). "
                "Format the updated workout plan clearly with exercise names, sets, reps, and duration."
            )
        else:
            # Initial request: create new workout plan
            prompt = (
                "Based on the following user profile, suggest a personalized workout plan "
                f"using the suggest_workout_plan tool{mcp_note}. Use ONLY exercises from the Kaggle "
                "gym exercise dataset (niharika41298/gym-exercise-data). Consider the user's age, "
                "daily goal, intensity preference, mood, injury restrictions, and available exercise time. "
            )
            if additional_requirements:
                prompt += f"\n\nAdditional requirements: {additional_requirements}\n"
            prompt += (
                "Format the workout plan clearly with exercise names, sets, reps, and duration.\n\n"
                f"User profile: {user_data}"
            )
        
        try:
            LOGGER.info(f"Sending prompt to ADK runner (length: {len(prompt)} chars)")
            LOGGER.debug(f"Prompt: {prompt[:500]}...")
            LOGGER.info(f"Model: {self.model}, User ID: workout-{username}, Session ID: {session_id}")
            
            # Check if runner.run is a generator
            # Note: user_id must be "web-user" for ADK runner to work properly
            # When we tried f"workout-{username}" or just username, it returned 0 events
            # The session_id is what actually maintains per-user session memory
            runner_result = self.runner.run(
                user_id="web-user",
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text=prompt)]
                ),
            )
            LOGGER.info(f"Runner result type: {type(runner_result)}")
            
            # Consume the generator - convert to list
            # Note: We can't use signal-based timeout here because Flask runs in a worker thread
            events = []
            try:
                LOGGER.info("Starting to consume generator...")
                for event in runner_result:
                    events.append(event)
                    event_type = type(event).__name__
                    LOGGER.info(f"Received event: {event_type}")
                    # Log tool calls if present
                    if hasattr(event, 'tool_call') and event.tool_call:
                        LOGGER.info(f"Tool call detected: {event.tool_call}")
                    if hasattr(event, 'tool_result') and event.tool_result:
                        LOGGER.info(f"Tool result received: {event.tool_result}")
                LOGGER.info(f"Generator exhausted. Total events: {len(events)}")
            except StopIteration:
                LOGGER.info("Generator raised StopIteration (normal end)")
            except Exception as gen_exc:
                LOGGER.exception(f"Exception while consuming generator: {gen_exc}")
                raise
            
            LOGGER.info(f"Received {len(events)} events from ADK runner")
            
            # Log details about each event
            for i, event in enumerate(events):
                event_type = type(event).__name__
                LOGGER.info(f"Event {i}: {event_type}")
                # Log all attributes of the event
                if hasattr(event, '__dict__'):
                    LOGGER.debug(f"  Event {i} attributes: {list(event.__dict__.keys())}")
                if hasattr(event, 'content'):
                    LOGGER.info(f"  Event {i} has content: {event.content}")
                if hasattr(event, 'tool_call'):
                    LOGGER.info(f"  Event {i} has tool_call: {event.tool_call}")
                if hasattr(event, 'tool_result'):
                    LOGGER.info(f"  Event {i} has tool_result: {event.tool_result}")
                if hasattr(event, 'text'):
                    LOGGER.info(f"  Event {i} has text: {event.text}")
            
            result = self._last_text_chunk(events) or ""
            LOGGER.info(f"Extracted workout plan (length: {len(result)} chars)")
            if not result:
                LOGGER.warning("No text content found in ADK events")
                # Try to get any text from events
                for i, event in enumerate(events):
                    if hasattr(event, 'content') and event.content:
                        LOGGER.warning(f"Event {i} content: {event.content}")
                    if hasattr(event, 'text'):
                        LOGGER.warning(f"Event {i} text: {event.text}")
            return result
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Failed to generate workout plan: %s", exc)
            import traceback
            LOGGER.error(f"Full traceback: {traceback.format_exc()}")
            return "Workout plan generation unavailable. Please check your configuration."

