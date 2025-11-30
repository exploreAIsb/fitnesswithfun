"""Kaggle MCP Server for querying gym exercise dataset directly from Kaggle."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastmcp import FastMCP
from kaggle.api.kaggle_api_extended import KaggleApi

try:
    import kagglehub
    KAGGLEHUB_AVAILABLE = True
except ImportError:
    KAGGLEHUB_AVAILABLE = False

LOGGER = logging.getLogger(__name__)

# Configure logging to use stderr for MCP servers (stdout is reserved for JSONRPC)
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stderr  # Use stderr to avoid breaking MCP JSONRPC protocol
)

# Suppress Kaggle API stdout messages that break MCP JSONRPC protocol
# We'll redirect stdout only during Kaggle API calls, not at module level
# to avoid breaking fastmcp's stdio server which needs stdout.buffer

BASE_DIR = Path(__file__).resolve().parent
EXERCISE_DB_PATH = BASE_DIR / "instance" / "exercises.db"
DATASET_DIR = BASE_DIR / "data" / "gym_exercise"
DATASET_NAME = "niharika41298/gym-exercise-data"

mcp = FastMCP("Kaggle Gym Exercise Dataset")

# Cache for in-memory dataset (optional optimization)
_dataset_cache: Optional[pd.DataFrame] = None


def load_dataset_from_kaggle(use_cache: bool = True) -> pd.DataFrame:
    """
    Load the Kaggle dataset efficiently using kagglehub (cached) or temporary download.
    
    Uses kagglehub library which downloads and caches the dataset locally,
    then loads it into pandas. Subsequent calls use the cached version.
    Falls back to temporary download if kagglehub is not available.
    
    Note: Kaggle doesn't provide streaming APIs, so some download is necessary.
    kagglehub caches downloads, making subsequent loads much faster.
    
    Args:
        use_cache: If True, use in-memory cached dataset if available
        
    Returns:
        DataFrame with the exercise data
    """
    global _dataset_cache
    
    # Return cached dataset if available
    if use_cache and _dataset_cache is not None:
        return _dataset_cache
    
    # Try using kagglehub for efficient loading (cached download, direct pandas load)
    if KAGGLEHUB_AVAILABLE:
        try:
            # Suppress kagglehub stdout messages during download
            old_stdout = sys.stdout
            sys.stdout = sys.stderr  # Redirect to stderr to avoid breaking MCP protocol
            
            try:
                # kagglehub downloads and caches the dataset, then loads directly into pandas
                # This is more efficient than temporary downloads as it caches for reuse
                dataset_path = kagglehub.dataset_download(DATASET_NAME)
            finally:
                sys.stdout = old_stdout  # Restore stdout
            
            # Convert to Path object if it's a string
            dataset_path = Path(dataset_path)
            
            # Find CSV files in the dataset path
            csv_files = list(dataset_path.glob("*.csv"))
            if not csv_files:
                # Also check subdirectories
                csv_files = list(dataset_path.rglob("*.csv"))
            
            if not csv_files:
                raise FileNotFoundError(f"No CSV files found in {dataset_path}")
            
            # Load the CSV file directly into pandas
            # kagglehub handles the download/caching, we just read the cached file
            csv_file = csv_files[0]
            LOGGER.info(f"Loading CSV file: {csv_file.name} from {dataset_path}")
            df = pd.read_csv(csv_file)
            
            # Cache the dataset in memory for even faster subsequent access
            if use_cache:
                _dataset_cache = df
            
            return df
        except Exception as e:
            LOGGER.warning(f"kagglehub loading failed: {e}, falling back to temporary download")
    
    # Fallback: Download to temporary location (if kagglehub not available or failed)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Suppress Kaggle API stdout completely (they break MCP JSONRPC protocol)
            # Redirect stdout to stderr temporarily for all Kaggle API operations
            old_stdout = sys.stdout
            sys.stdout = sys.stderr  # Redirect stdout to stderr for Kaggle API
            
            try:
                api = KaggleApi()
                api.authenticate()
            except Exception as auth_error:
                # Restore stdout
                sys.stdout = old_stdout
                
                error_msg = (
                    f"Kaggle API authentication failed: {auth_error}. "
                    "Please ensure kaggle.json is in ~/.kaggle/ or set KAGGLE_USERNAME and KAGGLE_KEY environment variables."
                )
                LOGGER.error(error_msg)
                raise RuntimeError(error_msg) from auth_error
            finally:
                # Always restore stdout
                sys.stdout = old_stdout
            
            temp_path = Path(temp_dir)
            # Use stderr for logging to avoid breaking MCP JSONRPC protocol (stdout is for JSONRPC)
            print(f"Downloading dataset {DATASET_NAME} to temporary location...", file=sys.stderr)
            try:
                # Redirect stdout to stderr during download to prevent breaking MCP protocol
                old_stdout = sys.stdout
                sys.stdout = sys.stderr
                try:
                    api.dataset_download_files(DATASET_NAME, path=str(temp_path), unzip=True)
                finally:
                    # Always restore stdout
                    sys.stdout = old_stdout
            except Exception as download_error:
                error_msg = f"Failed to download dataset {DATASET_NAME}: {download_error}"
                LOGGER.error(error_msg)
                raise RuntimeError(error_msg) from download_error
        
        # Find CSV files
        csv_files = list(temp_path.glob("*.csv"))
        if not csv_files:
            # Also check subdirectories
            csv_files = list(temp_path.rglob("*.csv"))
        
            if not csv_files:
                error_msg = f"No CSV files found in downloaded dataset {DATASET_NAME}"
                LOGGER.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            # Load the first CSV file
            try:
                df = pd.read_csv(csv_files[0])
                print(f"Successfully loaded dataset with {len(df)} rows", file=sys.stderr)
            except Exception as read_error:
                error_msg = f"Failed to read CSV file {csv_files[0]}: {read_error}"
                LOGGER.error(error_msg)
                raise RuntimeError(error_msg) from read_error
            
            # Cache the dataset
            if use_cache:
                _dataset_cache = df
            
            return df
    except Exception as e:
        LOGGER.error(f"Failed to load dataset from Kaggle: {e}")
        raise


def get_exercise_database() -> sqlite3.Connection:
    """
    Get connection to the exercise database (for backward compatibility).
    Falls back to loading from Kaggle if database doesn't exist.
    """
    if EXERCISE_DB_PATH.exists():
        conn = sqlite3.connect(str(EXERCISE_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
    else:
        # If no SQLite DB, we'll use direct Kaggle loading
        raise FileNotFoundError(
            f"Exercise database not found at {EXERCISE_DB_PATH}. "
            "The MCP server will query Kaggle directly instead."
        )


@mcp.tool()
def search_exercises(
    age: Optional[int] = None,
    daily_goal: Optional[str] = None,
    intensity: Optional[str] = None,
    mood: Optional[str] = None,
    restrictions: Optional[str] = None,
    exercise_minutes: Optional[int] = None,
    limit: int = 10,
    use_sqlite: bool = False,
) -> Dict[str, Any]:
    """
    Search for exercises from the Kaggle gym exercise dataset based on user attributes.
    
    This tool queries the Kaggle gym exercise dataset (niharika41298/gym-exercise-data)
    directly from Kaggle without requiring SQLite storage. It downloads the dataset
    temporarily, filters in memory, and returns results.
    
    Args:
        age: User's age for age-appropriate exercise selection
        daily_goal: User's daily fitness goal (e.g., "build muscle", "cardio", "flexibility")
        intensity: Desired workout intensity (low, moderate, high)
        mood: Current mood/energy level
        restrictions: Any physical restrictions or limitations
        exercise_minutes: Available time for exercise in minutes
        limit: Maximum number of exercises to return (default: 10)
        use_sqlite: If True, use SQLite database if available (default: False, queries Kaggle directly)
        
    Returns:
        Dictionary containing suggested exercises and filter details
    """
    # Try SQLite first if requested and available
    if use_sqlite:
        try:
            conn = get_exercise_database()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(exercises)")
            columns = [row[1] for row in cursor.fetchall()]
            
            query = "SELECT * FROM exercises WHERE 1=1"
            params = []
            
            if intensity:
                intensity_lower = intensity.lower()
                if "intensity" in columns:
                    query += " AND LOWER(intensity) LIKE ?"
                    params.append(f"%{intensity_lower}%")
                elif "difficulty" in columns:
                    query += " AND LOWER(difficulty) LIKE ?"
                    params.append(f"%{intensity_lower}%")
            
            if daily_goal:
                goal_lower = daily_goal.lower()
                for col in ["goal", "type", "category", "name", "title"]:
                    if col in columns:
                        query += f" AND LOWER({col}) LIKE ?"
                        params.append(f"%{goal_lower}%")
                        break
            
            if restrictions:
                restrictions_lower = restrictions.lower()
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
            
            if exercises:
                return {
                    "exercises": exercises,
                    "count": len(exercises),
                    "source": "sqlite",
                    "filters_applied": {
                        "age": age,
                        "daily_goal": daily_goal,
                        "intensity": intensity,
                        "mood": mood,
                        "restrictions": restrictions,
                        "exercise_minutes": exercise_minutes,
                    },
                }
        except FileNotFoundError:
            pass  # Fall through to Kaggle direct query
    
    # Load dataset directly from Kaggle
    try:
        df = load_dataset_from_kaggle(use_cache=True)
    except Exception as e:
        error_msg = f"Failed to load dataset from Kaggle: {e}"
        LOGGER.error(error_msg)
        return {
            "error": error_msg,
            "exercises": [],
            "count": 0,
            "source": "error",
            "filters_applied": {
                "age": age,
                "daily_goal": daily_goal,
                "intensity": intensity,
                "mood": mood,
                "restrictions": restrictions,
                "exercise_minutes": exercise_minutes,
            },
        }
    
    # Filter in memory using pandas
    filtered_df = df.copy()
    
    # Filter by intensity
    if intensity:
        intensity_lower = intensity.lower()
        for col in ["intensity", "difficulty", "level"]:
            if col in filtered_df.columns:
                filtered_df = filtered_df[
                    filtered_df[col].astype(str).str.lower().str.contains(intensity_lower, na=False)
                ]
                break
    
    # Filter by goal
    if daily_goal:
        goal_lower = daily_goal.lower()
        for col in ["goal", "type", "category", "name", "title"]:
            if col in filtered_df.columns:
                filtered_df = filtered_df[
                    filtered_df[col].astype(str).str.lower().str.contains(goal_lower, na=False)
                ]
                break
    
    # Filter out restrictions
    if restrictions:
        restrictions_lower = restrictions.lower()
        for col in ["equipment", "type", "category", "name"]:
            if col in filtered_df.columns:
                filtered_df = filtered_df[
                    ~filtered_df[col].astype(str).str.lower().str.contains(restrictions_lower, na=False)
                ]
                break
    
    # Limit results
    filtered_df = filtered_df.head(limit)
    
    # Convert to list of dicts and clean NaN values
    exercises = filtered_df.to_dict("records")
    
    # If no exercises found, return some default exercises
    if not exercises:
        exercises = df.head(limit).to_dict("records")
    
    # Clean NaN and None values from exercises
    import math
    cleaned_exercises = []
    for ex in exercises:
        cleaned = {}
        for k, v in ex.items():
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                # Convert numpy types to native Python types for JSON serialization
                if hasattr(v, 'item'):  # numpy scalar
                    cleaned[k] = v.item()
                else:
                    cleaned[k] = v
        cleaned_exercises.append(cleaned)
    
    return {
        "exercises": cleaned_exercises,
        "count": len(cleaned_exercises),
        "source": "kaggle_direct",
        "filters_applied": {
            "age": age,
            "daily_goal": daily_goal,
            "intensity": intensity,
            "mood": mood,
            "restrictions": restrictions,
            "exercise_minutes": exercise_minutes,
        },
    }


@mcp.tool()
def get_exercise_by_name(name: str, use_sqlite: bool = False) -> Dict[str, Any]:
    """
    Get a specific exercise by name from the Kaggle gym exercise dataset.
    
    Queries directly from Kaggle without requiring SQLite storage.
    
    Args:
        name: Name of the exercise to retrieve
        use_sqlite: If True, use SQLite database if available (default: False)
        
    Returns:
        Dictionary containing exercise details
    """
    # Try SQLite first if requested and available
    if use_sqlite:
        try:
            conn = get_exercise_database()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(exercises)")
            columns = [row[1] for row in cursor.fetchall()]
            
            for col in ["name", "title", "exercise", "exercise_name"]:
                if col in columns:
                    cursor.execute(f"SELECT * FROM exercises WHERE LOWER({col}) LIKE ? LIMIT 1", (f"%{name.lower()}%",))
                    row = cursor.fetchone()
                    if row:
                        conn.close()
                        return dict(row)
            conn.close()
        except FileNotFoundError:
            pass  # Fall through to Kaggle direct query
    
    # Load from Kaggle directly
    try:
        df = load_dataset_from_kaggle(use_cache=True)
    except Exception as e:
        error_msg = f"Failed to load dataset from Kaggle: {e}"
        LOGGER.error(error_msg)
        return {"error": error_msg}
    
    # Search in various columns
    name_lower = name.lower()
    for col in ["name", "title", "exercise", "exercise_name"]:
        if col in df.columns:
            matches = df[df[col].astype(str).str.lower().str.contains(name_lower, na=False)]
            if not matches.empty:
                return matches.iloc[0].to_dict()
    
    return {"error": f"Exercise '{name}' not found"}


@mcp.tool()
def download_kaggle_dataset() -> Dict[str, Any]:
    """
    Download the Kaggle gym exercise dataset and store it in SQLite.
    
    This tool downloads the dataset niharika41298/gym-exercise-data from Kaggle
    and stores it locally for querying. This only needs to be run once initially
    or when you want to refresh the dataset.
    
    Returns:
        Dictionary with download status and dataset information
    """
    try:
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        
        # Download from Kaggle
        api = KaggleApi()
        api.authenticate()
        
        dataset = "niharika41298/gym-exercise-data"
        print(f"Downloading dataset: {dataset}")
        api.dataset_download_files(dataset, path=str(DATASET_DIR), unzip=True)
        
        # Load and store in SQLite
        csv_files = list(DATASET_DIR.glob("*.csv"))
        if not csv_files:
            return {"error": "No CSV files found after download"}
        
        df = pd.read_csv(csv_files[0])
        
        # Store in SQLite
        conn = sqlite3.connect(str(EXERCISE_DB_PATH))
        df.to_sql("exercises", conn, if_exists="replace", index=False)
        conn.close()
        
        return {
            "status": "success",
            "message": f"Dataset downloaded and stored successfully",
            "rows": len(df),
            "columns": list(df.columns),
            "database_path": str(EXERCISE_DB_PATH),
        }
    except Exception as e:
        error_msg = f"Failed to download dataset: {e}"
        LOGGER.error(error_msg)
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to download dataset. Make sure Kaggle API credentials are configured. "
                       "Place kaggle.json in ~/.kaggle/ or set KAGGLE_USERNAME and KAGGLE_KEY environment variables."
        }


if __name__ == "__main__":
    mcp.run()

