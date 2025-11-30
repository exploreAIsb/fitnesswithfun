## ADK + Gemini Wellness Lookup with Kaggle Workout Plans

This sample shows how to wire the Google Agent Development Kit (ADK) into a tiny Flask UI that queries a local SQLite database. When a username exists you'll see their stored profile along with a short Gemini generated summary. Otherwise the UI asks for more details and persists the profile.

**New Feature**: The app now generates personalized workout plans using the [Kaggle gym exercise dataset](https://www.kaggle.com/datasets/niharika41298/gym-exercise-data) **via MCP (Model Context Protocol) server**. The ADK agent uses an MCP server tool to query this dataset based on user attributes (age, daily goal, intensity, mood, restrictions, exercise time).

### Prerequisites

- Python 3.11+
- Google AI Studio API key with access to the Gemini models
- Kaggle API credentials (for downloading the exercise dataset)

### Setup

1. Create a virtual environment and install dependencies:
   ```bash
   cd /Users/owner/scratch2
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `env.example` to `.env` and set your credentials:
   ```bash
   cp env.example .env
   # edit GOOGLE_API_KEY, ADK_MODEL, DATABASE_PATH as needed
   ```

3. Set up Kaggle API credentials:
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

4. **Dataset Access (Automatic)**:
   
   The MCP server automatically downloads and caches the Kaggle dataset on first use using `kagglehub`.
   **No manual download is required!** The dataset is cached for fast subsequent queries.

5. (Optional) Rebuild the user database:
   ```bash
   python init_db.py --drop
   ```

### Run the app

```bash
flask --app app run --debug
```

Visit http://127.0.0.1:5000 and try the seeded users `alex` or `jordan`. Creating a brand new profile will store it in SQLite and display a Gemini powered summary via ADK.

**Workout Plan Generation**: After viewing a user profile, click the "Generate Workout Plan" button to get a personalized workout plan based on the Kaggle gym exercise dataset. The ADK agent uses an **MCP server** (`kaggle_mcp_server.py`) to query the dataset using the user's age, daily goal, intensity, mood, restrictions, and available exercise time. The MCP server ensures all queries go through the standardized Model Context Protocol.

### Notes

- The ADK integration lives in `adk_client.py`, where a `LlmAgent` uses the `gemini-2.0-flash` model by default. Set `ADK_MODEL` to try different Gemini variants.
- **MCP Server Integration**: The app uses an MCP server (`kaggle_mcp_server.py`) built with `fastmcp` to provide tools for querying and downloading the Kaggle dataset. The MCP server includes:
  - `search_exercises`: Query exercises based on user attributes **directly from Kaggle** (no SQLite required)
  - `get_exercise_by_name`: Get a specific exercise by name **directly from Kaggle**
  - `download_kaggle_dataset`: Download and populate the dataset (optional, for SQLite caching)
  
  **Key Feature**: The MCP server can query the Kaggle dataset **without requiring SQLite storage**. It uses `kagglehub` library which efficiently downloads and caches the dataset, then loads it directly into pandas for in-memory filtering. The first query downloads the dataset (cached by kagglehub), and subsequent queries use the cached version for fast access. The MCP server handles everything dynamically - no manual setup required.
  
  **Note**: Kaggle doesn't provide streaming APIs, so the dataset must be downloaded at least once. However, `kagglehub` caches downloads efficiently, making subsequent queries very fast without re-downloading.
  
  The MCP client (`mcp_client_tool.py`) wraps these MCP tools for use with ADK agents.
- The workout plan tool uses the MCP server to query the Kaggle dataset. By default, it queries **directly from Kaggle** without requiring SQLite storage. The dataset is downloaded temporarily, filtered in memory, and results are returned. The ADK agent calls MCP tools via `mcp_client_tool.py` to generate personalized workout plans.
- `DATABASE_PATH` lets you move the SQLite file elsewhere (default is `instance/users.db`).
- The UI intentionally keeps things simple with vanilla JS + fetch; feel free to swap in your preferred frontend stack.
- The workout plan generation uses ONLY exercises from the Kaggle dataset via MCP server, ensuring all suggestions are based on real exercise data and follow the Model Context Protocol standard.

