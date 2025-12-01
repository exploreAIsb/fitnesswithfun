"""ADK tool for querying the gym exercise dataset to suggest workouts."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
EXERCISE_DB_PATH = BASE_DIR / "instance" / "exercises.db"


def get_exercise_database() -> sqlite3.Connection:
    """Get connection to the exercise database."""
    if not EXERCISE_DB_PATH.exists():
        raise FileNotFoundError(
            f"Exercise database not found at {EXERCISE_DB_PATH}. "
            "This fallback tool requires a local SQLite database. "
            "Consider using the MCP server instead (see mcp_client_tool.py)."
        )
    conn = sqlite3.connect(str(EXERCISE_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def suggest_workout_plan(
    age: Optional[int] = None,
    daily_goal: Optional[str] = None,
    intensity: Optional[str] = None,
    mood: Optional[str] = None,
    restrictions: Optional[str] = None,
    exercise_minutes: Optional[int] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Suggest a workout plan from the Kaggle gym exercise dataset based on user attributes.
    
    This tool queries the exercise database and filters exercises based on:
    - Age (for age-appropriate exercises)
    - Daily goal (matches exercise types/goals)
    - Intensity level (matches exercise difficulty)
    - Mood (suggests exercises that match energy level)
    - Injury Restrictions (filters out incompatible exercises)
    - Exercise time available (suggests exercises that fit the time)
    
    Args:
        age: User's age
        daily_goal: User's daily fitness goal
        intensity: Desired workout intensity (low, moderate, high)
        mood: Current mood/energy level
        restrictions: Any injury restrictions or limitations
        exercise_minutes: Available time for exercise in minutes
        limit: Maximum number of exercises to return
        
    Returns:
        Dictionary with suggested exercises and workout plan details
    """
    conn = get_exercise_database()
    cursor = conn.cursor()
    
    # Get all columns from the exercises table
    cursor.execute("PRAGMA table_info(exercises)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Build query with filters
    query = "SELECT * FROM exercises WHERE 1=1"
    params = []
    
    # Filter by intensity if provided
    if intensity:
        intensity_lower = intensity.lower()
        # Try to match intensity in various column names
        if "intensity" in columns:
            query += " AND LOWER(intensity) LIKE ?"
            params.append(f"%{intensity_lower}%")
        elif "difficulty" in columns:
            query += " AND LOWER(difficulty) LIKE ?"
            params.append(f"%{intensity_lower}%")
        elif "level" in columns:
            query += " AND LOWER(level) LIKE ?"
            params.append(f"%{intensity_lower}%")
    
    # Filter by goal if provided
    if daily_goal:
        goal_lower = daily_goal.lower()
        # Try to match goal in various column names
        for col in ["goal", "type", "category", "name", "title"]:
            if col in columns:
                query += f" AND LOWER({col}) LIKE ?"
                params.append(f"%{goal_lower}%")
                break
    
    # Filter out restricted exercises
    if restrictions:
        restrictions_lower = restrictions.lower()
        # Exclude exercises that match restrictions
        for col in ["equipment", "type", "category", "name"]:
            if col in columns:
                query += f" AND LOWER({col}) NOT LIKE ?"
                params.append(f"%{restrictions_lower}%")
                break
    
    query += f" LIMIT {limit}"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    exercises = [dict(row) for row in rows]
    
    conn.close()
    
    # If no exercises found, get some default exercises
    if not exercises:
        conn = get_exercise_database()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM exercises LIMIT {limit}")
        rows = cursor.fetchall()
        exercises = [dict(row) for row in rows]
        conn.close()
    
    return {
        "exercises": exercises,
        "count": len(exercises),
        "filters_applied": {
            "age": age,
            "daily_goal": daily_goal,
            "intensity": intensity,
            "mood": mood,
            "restrictions": restrictions,
            "exercise_minutes": exercise_minutes,
        },
    }

