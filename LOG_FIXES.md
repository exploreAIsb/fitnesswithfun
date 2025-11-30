# Log Issues and Fixes

## Issues Found in Logs

### 1. **Kaggle API Authentication Errors Breaking MCP Protocol**
**Error**: 
```
ERROR: Failed to parse JSONRPC message from server
Invalid JSON: expected value at line 1 column 1
input_value="Could not find kaggle.json..."
```

**Root Cause**: 
- Kaggle API library prints error messages to `stdout`
- MCP protocol uses `stdout` for JSONRPC communication
- Any non-JSON output to `stdout` breaks the MCP protocol

**Fix Applied**:
- Redirected all logging to `stderr` 
- Created `StdoutToStderr` wrapper class to redirect stdout to stderr
- Suppressed stdout during Kaggle API operations
- Added proper error handling with structured error responses

### 2. **Missing Error Context**
**Issue**: Errors were not providing enough context for debugging

**Fix Applied**:
- Added comprehensive logging with `LOGGER.error()`, `LOGGER.warning()`, `LOGGER.info()`
- Error messages now include setup instructions
- Structured error responses instead of exceptions

### 3. **MCP Protocol Violations**
**Issue**: Print statements and error messages going to stdout

**Fix Applied**:
- All print statements redirected to `stderr`
- Logging configured to use `stderr` stream
- Kaggle API stdout suppressed during operations

## Current Log Status

### Working:
- ✅ Logging configured to use stderr
- ✅ Error handling with structured responses
- ✅ MCP protocol compliance (stdout reserved for JSONRPC)

### Known Issues:
- ⚠️ Kaggle API credentials required for full functionality
- ⚠️ First-time dataset download may take time
- ⚠️ Kaggle API library may still print to stdout during import (mitigated by redirect)

## How to Check Logs

1. **Application Logs**: Check stderr output when running Flask app
2. **MCP Server Logs**: Check stderr when MCP server runs
3. **Error Responses**: Check API responses for structured error messages

## Testing Logs

Run with logging enabled:
```bash
python -c "import logging; logging.basicConfig(level=logging.INFO); from mcp_client_tool import suggest_workout_plan_via_mcp; result = suggest_workout_plan_via_mcp(limit=2)"
```

Check for errors in stderr (not stdout).

