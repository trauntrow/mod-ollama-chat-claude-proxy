#!/usr/bin/env python3
"""
Ollama-to-Claude API Proxy
===========================
A lightweight proxy server that implements the Ollama API interface
but forwards requests to Anthropic's Claude API.

This allows mod-ollama-chat (and any other Ollama client) to use
Claude models without any code modifications — no recompilation needed.

Usage:
    1. Set your Anthropic API key:
       Linux/macOS:  export ANTHROPIC_API_KEY="sk-ant-..."
       Windows CMD:  set ANTHROPIC_API_KEY=sk-ant-...
       PowerShell:   $env:ANTHROPIC_API_KEY="sk-ant-..."

    2. Run the proxy:
       python ollama_claude_proxy.py

    3. Configure mod-ollama-chat to point to this proxy:
       OllamaChat.Url = "http://localhost:11435/api/generate"
       OllamaChat.Model = "claude-sonnet"

Repository: https://github.com/YOUR_USERNAME/ollama-claude-proxy
License: MIT
"""

import json
import os
import sys
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration (all configurable via environment variables)
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_API_URL = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "512"))
PROXY_HOST = os.environ.get("PROXY_HOST", "0.0.0.0")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "11435"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ollama-claude-proxy")

# ---------------------------------------------------------------------------
# Model mapping — friendly names to actual Anthropic model strings
# ---------------------------------------------------------------------------

MODEL_MAP = {
    # Friendly short names for mod-ollama-chat config
    "claude-sonnet":                "claude-sonnet-4-20250514",
    "claude-sonnet-4":              "claude-sonnet-4-20250514",
    "claude-haiku":                 "claude-haiku-4-20250414",
    "claude-haiku-4":               "claude-haiku-4-20250414",
    "claude-opus":                  "claude-opus-4-20250514",
    "claude-opus-4":                "claude-opus-4-20250514",
    # Full model ID pass-through
    "claude-sonnet-4-20250514":     "claude-sonnet-4-20250514",
    "claude-haiku-4-20250414":      "claude-haiku-4-20250414",
    "claude-opus-4-20250514":       "claude-opus-4-20250514",
    # Older model names
    "claude-3-5-sonnet":            "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku":             "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022":   "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022":    "claude-3-5-haiku-20241022",
}

# Models advertised on /api/tags
AVAILABLE_MODELS = [
    {
        "name": "claude-sonnet",
        "model": "claude-sonnet",
        "size": 0,
        "digest": "claude-sonnet-4-20250514",
        "details": {
            "parent_model": "",
            "format": "api",
            "family": "claude",
            "families": ["claude"],
            "parameter_size": "N/A",
            "quantization_level": "none",
        },
        "modified_at": "2025-05-14T00:00:00Z",
    },
    {
        "name": "claude-haiku",
        "model": "claude-haiku",
        "size": 0,
        "digest": "claude-haiku-4-20250414",
        "details": {
            "parent_model": "",
            "format": "api",
            "family": "claude",
            "families": ["claude"],
            "parameter_size": "N/A",
            "quantization_level": "none",
        },
        "modified_at": "2025-04-14T00:00:00Z",
    },
    {
        "name": "claude-opus",
        "model": "claude-opus",
        "size": 0,
        "digest": "claude-opus-4-20250514",
        "details": {
            "parent_model": "",
            "format": "api",
            "family": "claude",
            "families": ["claude"],
            "parameter_size": "N/A",
            "quantization_level": "none",
        },
        "modified_at": "2025-05-14T00:00:00Z",
    },
]


def resolve_model(requested: str) -> str:
    """Resolve a friendly model name to an Anthropic model ID."""
    lowered = requested.lower().strip()
    if lowered in MODEL_MAP:
        return MODEL_MAP[lowered]
    log.warning("Unknown model '%s', falling back to %s", requested, ANTHROPIC_MODEL)
    return ANTHROPIC_MODEL


# ---------------------------------------------------------------------------
# Ollama → Anthropic message conversion
# ---------------------------------------------------------------------------

def convert_ollama_to_anthropic(ollama_messages: list) -> tuple:
    """
    Convert Ollama-style messages to Anthropic format.

    Ollama uses:   {"role": "system"|"user"|"assistant", "content": "..."}
    Anthropic uses: separate `system` param + messages with "user"/"assistant" only.

    Returns: (system_prompt, messages)
    """
    system_prompt = None
    anthropic_messages = []

    for msg in ollama_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            if system_prompt is None:
                system_prompt = content
            else:
                system_prompt += "\n\n" + content
        elif role in ("user", "assistant"):
            anthropic_messages.append({"role": role, "content": content})
        else:
            anthropic_messages.append({"role": "user", "content": content})

    # Anthropic requires at least one user message
    if not anthropic_messages:
        anthropic_messages.append({"role": "user", "content": "Hello"})

    # Anthropic requires messages to alternate user/assistant — merge consecutive same-role
    merged = []
    for msg in anthropic_messages:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n" + msg["content"]
        else:
            merged.append(dict(msg))

    # Ensure first message is from user
    if merged and merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": "(continuing conversation)"})

    return system_prompt, merged


def call_anthropic(model: str, system_prompt=None,
                   messages: list = None, temperature: float = None,
                   max_tokens: int = None) -> str:
    """Call the Anthropic Messages API and return the assistant's text."""

    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Set it before running the proxy:\n"
            "  Linux/macOS:  export ANTHROPIC_API_KEY='sk-ant-...'\n"
            "  Windows CMD:  set ANTHROPIC_API_KEY=sk-ant-...\n"
            "  PowerShell:   $env:ANTHROPIC_API_KEY='sk-ant-...'"
        )

    body = {
        "model": model,
        "max_tokens": max_tokens or ANTHROPIC_MAX_TOKENS,
        "messages": messages or [],
    }

    if system_prompt:
        body["system"] = system_prompt
    if temperature is not None:
        body["temperature"] = temperature

    payload = json.dumps(body).encode("utf-8")

    req = Request(
        ANTHROPIC_API_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )

    log.debug("Anthropic request: model=%s, messages=%d, max_tokens=%d",
              model, len(messages or []), body["max_tokens"])

    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        log.error("Anthropic API error %d: %s", e.code, error_body)
        raise RuntimeError(f"Anthropic API returned {e.code}: {error_body}")
    except URLError as e:
        log.error("Anthropic API connection error: %s", e.reason)
        raise RuntimeError(f"Cannot reach Anthropic API: {e.reason}")

    # Extract text from response content blocks
    text_parts = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block["text"])

    result = "\n".join(text_parts)
    log.debug("Anthropic response: %d chars", len(result))
    return result


# ---------------------------------------------------------------------------
# Ollama-compatible response builders
# ---------------------------------------------------------------------------

def build_chat_response(model_name: str, content: str, done: bool = True) -> dict:
    """Build a response matching the Ollama /api/chat format."""
    return {
        "model": model_name,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "message": {
            "role": "assistant",
            "content": content,
        },
        "done": done,
        "done_reason": "stop" if done else "",
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": 0,
        "prompt_eval_duration": 0,
        "eval_count": 0,
        "eval_duration": 0,
    }


def build_generate_response(model_name: str, content: str, done: bool = True) -> dict:
    """Build a response matching the Ollama /api/generate format."""
    return {
        "model": model_name,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "response": content,
        "done": done,
        "done_reason": "stop" if done else "",
        "context": [],
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": 0,
        "prompt_eval_duration": 0,
        "eval_count": 0,
        "eval_duration": 0,
    }


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class OllamaProxyHandler(BaseHTTPRequestHandler):
    """Handles Ollama-compatible HTTP requests and proxies to Claude."""

    def log_message(self, format, *args):
        log.info(format, *args)

    def _send_json(self, data, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_ndjson_lines(self, lines: list, status: int = 200):
        """Send newline-delimited JSON (streaming simulation)."""
        self.send_response(status)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for line in lines:
            chunk = json.dumps(line) + "\n"
            chunk_bytes = chunk.encode("utf-8")
            self.wfile.write(f"{len(chunk_bytes):x}\r\n".encode())
            self.wfile.write(chunk_bytes)
            self.wfile.write(b"\r\n")
        self.wfile.write(b"0\r\n\r\n")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length > 0 else b""

    # ---- GET routes ----

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "" or path == "/":
            self._send_text("Ollama is running")
        elif path == "/api/tags":
            self._send_json({"models": AVAILABLE_MODELS})
        elif path == "/api/version":
            self._send_json({"version": "ollama-claude-proxy-1.0.0"})
        elif path.startswith("/api/show"):
            self._send_json(self._model_info())
        elif path == "/api/ps":
            self._send_json({"models": []})
        else:
            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)

    # ---- POST routes ----

    def do_POST(self):
        path = self.path.rstrip("/")
        raw_body = self._read_body()

        try:
            body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, status=400)
            return

        if path == "/api/chat":
            self._handle_chat(body)
        elif path == "/api/generate":
            self._handle_generate(body)
        elif path == "/api/show":
            self._send_json(self._model_info())
        elif path == "/api/tags":
            self._send_json({"models": AVAILABLE_MODELS})
        else:
            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

    # ---- Helpers ----

    @staticmethod
    def _model_info():
        return {
            "modelfile": "# Claude model via proxy",
            "parameters": "",
            "template": "",
            "details": {
                "parent_model": "",
                "format": "api",
                "family": "claude",
                "families": ["claude"],
                "parameter_size": "N/A",
                "quantization_level": "none",
            },
        }

    def _handle_chat(self, body: dict):
        """Handle POST /api/chat."""
        requested_model = body.get("model", "claude-sonnet")
        messages = body.get("messages", [])
        stream = body.get("stream", True)
        options = body.get("options", {})

        temperature = options.get("temperature")
        max_tokens_opt = options.get("num_predict") or options.get("max_tokens")
        anthropic_model = resolve_model(requested_model)

        log.info("Chat request: model=%s -> %s, messages=%d, stream=%s",
                 requested_model, anthropic_model, len(messages), stream)

        try:
            system_prompt, anthropic_messages = convert_ollama_to_anthropic(messages)
            response_text = call_anthropic(
                model=anthropic_model,
                system_prompt=system_prompt,
                messages=anthropic_messages,
                temperature=temperature,
                max_tokens=int(max_tokens_opt) if max_tokens_opt else None,
            )

            if stream is False:
                self._send_json(build_chat_response(requested_model, response_text, done=True))
            else:
                self._send_ndjson_lines([
                    build_chat_response(requested_model, response_text, done=False),
                    build_chat_response(requested_model, "", done=True),
                ])
        except Exception as e:
            log.error("Error handling chat: %s", e)
            err = build_chat_response(requested_model, f"[Proxy Error] {e}", done=True)
            if stream is False:
                self._send_json(err, status=500)
            else:
                self._send_ndjson_lines([err])

    def _handle_generate(self, body: dict):
        """Handle POST /api/generate — used by mod-ollama-chat."""
        requested_model = body.get("model", "claude-sonnet")
        prompt = body.get("prompt", "")
        system = body.get("system")
        stream = body.get("stream", True)
        options = body.get("options", {})

        temperature = options.get("temperature")
        max_tokens_opt = options.get("num_predict") or options.get("max_tokens")
        anthropic_model = resolve_model(requested_model)

        log.info("Generate request: model=%s -> %s, prompt=%d chars",
                 requested_model, anthropic_model, len(prompt))

        try:
            messages = [{"role": "user", "content": prompt}]
            response_text = call_anthropic(
                model=anthropic_model,
                system_prompt=system,
                messages=messages,
                temperature=temperature,
                max_tokens=int(max_tokens_opt) if max_tokens_opt else None,
            )

            if stream is False:
                self._send_json(build_generate_response(requested_model, response_text, done=True))
            else:
                self._send_ndjson_lines([
                    build_generate_response(requested_model, response_text, done=False),
                    build_generate_response(requested_model, "", done=True),
                ])
        except Exception as e:
            log.error("Error handling generate: %s", e)
            err = build_generate_response(requested_model, f"[Proxy Error] {e}", done=True)
            if stream is False:
                self._send_json(err, status=500)
            else:
                self._send_ndjson_lines([err])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not ANTHROPIC_API_KEY:
        print("=" * 60)
        print("  WARNING: ANTHROPIC_API_KEY is not set!")
        print("  Set it before running:")
        print("    Linux/macOS:  export ANTHROPIC_API_KEY='sk-ant-...'")
        print("    Windows CMD:  set ANTHROPIC_API_KEY=sk-ant-...")
        print("    PowerShell:   $env:ANTHROPIC_API_KEY='sk-ant-...'")
        print("=" * 60)
        print()

    server = HTTPServer((PROXY_HOST, PROXY_PORT), OllamaProxyHandler)

    print(f"""
======================================================
  Ollama -> Claude API Proxy
======================================================
  Listening on:  http://{PROXY_HOST}:{PROXY_PORT}
  Claude model:  {ANTHROPIC_MODEL}
  API key set:   {'Yes' if ANTHROPIC_API_KEY else 'NO - SET ANTHROPIC_API_KEY!'}
------------------------------------------------------
  mod-ollama-chat config:
    OllamaChat.Url = "http://localhost:{PROXY_PORT}/api/generate"
    OllamaChat.Model = "claude-sonnet"
======================================================
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down proxy...")
        server.shutdown()


if __name__ == "__main__":
    main()
