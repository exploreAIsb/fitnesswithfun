#!/bin/bash

# Flask App Runner Script
# Checks if port is available and kills any process using it before starting the app

set -e  # Exit on error

# Get port from environment variable or use default
PORT=${PORT:-5001}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting Flask app on port $PORT..."

# Check if port is in use
check_port() {
    local port=$1
    local pid=$(lsof -ti:$port 2>/dev/null || echo "")
    
    if [ -n "$pid" ]; then
        echo "⚠️  Port $port is in use by process $pid"
        
        # Get process info
        local process_info=$(ps -p $pid -o comm=,args= 2>/dev/null || echo "unknown process")
        echo "   Process: $process_info"
        
        # Kill the process
        echo "🛑 Killing process $pid..."
        kill -9 $pid 2>/dev/null || true
        sleep 1
        
        # Verify port is now free
        if lsof -ti:$port >/dev/null 2>&1; then
            echo "❌ Failed to free port $port. Please check manually."
            exit 1
        else
            echo "✅ Port $port is now free"
        fi
    else
        echo "✅ Port $port is available"
    fi
}

# Check and free the port
check_port $PORT

# Activate virtual environment if it exists
if [ -d "$SCRIPT_DIR/.venv" ]; then
    echo "📦 Activating virtual environment..."
    source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -d "$SCRIPT_DIR/venv" ]; then
    echo "📦 Activating virtual environment..."
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Export PORT for the Flask app
export PORT=$PORT

# Change to script directory
cd "$SCRIPT_DIR"

# Run the Flask app
echo "🎯 Starting Flask app..."
python app.py

