@echo off
REM ============================================================
REM  Ollama -> Claude API Proxy - Windows Start Script
REM ============================================================
REM  Set your Anthropic API key below (replace YOUR-KEY-HERE)
REM  Get a key at: https://console.anthropic.com/
REM ============================================================

set ANTHROPIC_API_KEY=YOUR-KEY-HERE
set ANTHROPIC_MAX_TOKENS=512
set PROXY_PORT=11435
set LOG_LEVEL=INFO

echo Starting Ollama Claude Proxy...
python "%~dp0ollama_claude_proxy.py"

pause
