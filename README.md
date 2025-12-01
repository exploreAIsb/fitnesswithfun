## ADK + Gemini Wellness Lookup with Kaggle Workout Plans

This sample shows how to wire the Google Agent Development Kit (ADK) into a tiny Flask UI that queries a local SQLite database. When a username exists you'll see their stored profile along with a short Gemini generated summary. Otherwise the UI asks for more details and persists the profile.

**New Feature**: The app now generates personalized workout plans using the [Kaggle gym exercise dataset](https://www.kaggle.com/datasets/niharika41298/gym-exercise-data) **via MCP (Model Context Protocol) server**. The ADK agent uses an MCP server tool to query this dataset based on user attributes (age, daily goal, intensity, mood, injury restrictions, exercise time).

### Prerequisites

- Python 3.11+
- Google AI Studio API key with access to the Gemini models
- Kaggle API credentials (for downloading the exercise dataset)

### Setup

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone <repository-url>
   cd <project-directory>
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file and set your credentials:
   ```bash
   # Create .env file with the following variables:
   GOOGLE_API_KEY=your_google_api_key_here
   ADK_MODEL=gemini-2.0-flash
   DATABASE_PATH=instance/users.db
   LOG_LEVEL=INFO
   LOG_FILE=app.log
   ```
   - Get your Google API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - `ADK_MODEL` defaults to `gemini-2.0-flash` if not set
   - `DATABASE_PATH` defaults to `instance/users.db` if not set

4. Set up Kaggle API credentials (required for workout plan generation):
   - Get your Kaggle API token from https://www.kaggle.com/settings (Account → API → Create New Token)
   - Place `kaggle.json` in `~/.kaggle/` directory:
     ```bash
     mkdir -p ~/.kaggle
     cp kaggle.json ~/.kaggle/
     chmod 600 ~/.kaggle/kaggle.json
     ```
   - Or set environment variables:
     ```bash
     export KAGGLE_USERNAME=your_username
     export KAGGLE_KEY=your_api_key
     ```

5. **Dataset Access (Automatic)**:
   
   The MCP server automatically downloads and caches the Kaggle dataset on first use using `kagglehub`.
   **No manual download is required!** The dataset is cached for fast subsequent queries.

6. The database will be automatically created with seed data on first run.

### Run the app

```bash
# Activate virtual environment first
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Run the app
python app.py
# OR
flask --app app run --debug
```

Visit http://127.0.0.1:5000 and try the seeded users `alex` or `jordan`. Creating a brand new profile will store it in SQLite and display a Gemini powered summary via ADK.

**Features:**
- **User Profile Management**: Look up existing users or create new profiles with age, height (inches), weight (lbs), exercise minutes, intensity, mood, injury restrictions, goals, and daily goals.
- **Profile Editing**: After looking up a user, click "Edit Profile" to update their information.
- **Workout Plan Generation**: After viewing a user profile, click the "Generate Workout Plan" button to get a personalized workout plan based on the Kaggle gym exercise dataset. The ADK agent uses an **MCP server** (`kaggle_mcp_server.py`) to query the dataset using the user's age, daily goal, intensity, mood, injury restrictions, and available exercise time.
- **Workout Plan Refinement**: After generating a workout plan, you can refine it by adding additional requirements. The ADK agent uses **session memory** to remember previous context and build upon the existing plan.
- **Logging**: All logs are written to `logs/app.log` and `logs/adk_client.log` for debugging.

### Notes

- **ADK Integration**: The ADK integration lives in `adk_client.py`, where a `LlmAgent` uses the `gemini-2.0-flash` model by default. Set `ADK_MODEL` in `.env` to try different Gemini variants.
- **ADK Session Memory**: The app uses ADK session memory to maintain conversation context for workout plan refinement. Each user gets their own persistent session, allowing the agent to remember previous requirements and build upon existing plans.
- **MCP Server Integration**: The app uses an MCP server (`kaggle_mcp_server.py`) built with `fastmcp` to provide tools for querying and downloading the Kaggle dataset. The MCP server includes:
  - `search_exercises`: Query exercises based on user attributes **directly from Kaggle** (no SQLite required)
  - `get_exercise_by_name`: Get a specific exercise by name **directly from Kaggle**
  - `download_kaggle_dataset`: Download and populate the dataset (optional, for SQLite caching)
  
  **Key Feature**: The MCP server can query the Kaggle dataset **without requiring SQLite storage**. It uses `kagglehub` library which efficiently downloads and caches the dataset, then loads it directly into pandas for in-memory filtering. The first query downloads the dataset (cached by kagglehub), and subsequent queries use the cached version for fast access. The MCP server handles everything dynamically - no manual setup required.
  
  **Note**: Kaggle doesn't provide streaming APIs, so the dataset must be downloaded at least once. However, `kagglehub` caches downloads efficiently, making subsequent queries very fast without re-downloading.
  
  The MCP client (`mcp_client_tool.py`) wraps these MCP tools for use with ADK agents.
- **Workout Plan Generation**: The workout plan tool uses the MCP server to query the Kaggle dataset. By default, it queries **directly from Kaggle** without requiring SQLite storage. The dataset is downloaded temporarily, filtered in memory, and results are returned. The ADK agent calls MCP tools via `mcp_client_tool.py` to generate personalized workout plans.
- **Units**: The app uses US standard units - height in inches and weight in pounds (lbs).
- **Injury Restrictions**: Users can specify injury restrictions (e.g., "knee injury", "back pain") which are used to filter out incompatible exercises.
- **Database**: `DATABASE_PATH` lets you move the SQLite file elsewhere (default is `instance/users.db`). The database is automatically created with seed data on first run.
- **Logging**: Logs are written to `logs/app.log` and `logs/adk_client.log`. Set `LOG_LEVEL` in `.env` to control logging verbosity (DEBUG, INFO, WARNING, ERROR).
- **UI**: The UI intentionally keeps things simple with vanilla JS + fetch; feel free to swap in your preferred frontend stack.
- **Data Source**: The workout plan generation uses ONLY exercises from the Kaggle dataset via MCP server, ensuring all suggestions are based on real exercise data and follow the Model Context Protocol standard.

