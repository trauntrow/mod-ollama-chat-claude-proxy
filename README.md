# Ollama → Claude API Proxy for mod-ollama-chat

A zero-dependency Python proxy that lets [mod-ollama-chat](https://github.com/DustinHendrickson/mod-ollama-chat) (AzerothCore Playerbots) use **Anthropic Claude** (Sonnet, Haiku, Opus) instead of local Ollama models.

No C++ changes. No recompilation. Just run the proxy and point your config at it.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)

## How It Works

```
┌──────────────┐     /api/generate    ┌──────────────┐    /v1/messages     ┌──────────────┐
│  AzerothCore │ ──────────────────► │  This Proxy   │ ─────────────────► │  Claude API  │
│  mod-ollama  │                     │  (Python)     │                    │  (Anthropic) │
│  -chat       │ ◄────────────────── │  port 11435   │ ◄───────────────── │              │
└──────────────┘   Ollama response   └──────────────┘  Claude response    └──────────────┘
```

The proxy translates between the Ollama API format and the Anthropic Messages API:

- **System prompts** — Ollama embeds them in messages; Anthropic takes them as a separate parameter
- **Message role conversion** — Merges consecutive same-role messages as required by Claude
- **Streaming simulation** — Returns full response as NDJSON lines compatible with mod-ollama-chat's async reader
- **Model name mapping** — Use friendly names like `claude-sonnet` in your config
- **Both endpoints** — Supports `/api/generate` and `/api/chat`, plus `/api/tags` and health checks

## Why Claude over Local Models?

| | Local Ollama (e.g. Qwen 7B) | Claude Sonnet |
|---|---|---|
| **Instruction following** | Often ignores constraints | Follows complex prompts precisely |
| **Roleplay quality** | Generic, breaks character | Stays in character, has personality |
| **WoW knowledge** | Limited training data | Deep knowledge of WoW lore & slang |
| **Response consistency** | Hit or miss | Reliably good |
| **Hardware needed** | GPU with VRAM | None (cloud API) |
| **Cost** | Free (electricity) | ~$0.001–0.01 per bot response |

## Quick Start

### 1. Get an Anthropic API Key

Sign up at [console.anthropic.com](https://console.anthropic.com/) and create an API key.

### 2. Clone This Repo

```bash
git clone https://github.com/YOUR_USERNAME/ollama-claude-proxy.git
cd ollama-claude-proxy
```

### 3. Set Your API Key & Run

**Windows CMD:**
```cmd
set ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE
python ollama_claude_proxy.py
```

**Windows PowerShell:**
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-api03-YOUR-KEY-HERE"
python ollama_claude_proxy.py
```

**Linux / macOS:**
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-YOUR-KEY-HERE"
python3 ollama_claude_proxy.py
```

### 4. Configure mod-ollama-chat

Edit your `mod-ollama-chat.conf` — only two lines need to change:

```ini
# Point to the proxy instead of Ollama
OllamaChat.Url = http://localhost:11435/api/generate

# Use a Claude model name
OllamaChat.Model = claude-sonnet
```

### 5. Reload

Use `.ollama reload` in-game (GM command) or restart your worldserver.

**That's it.** Your bots are now powered by Claude.

## Available Model Names

Use any of these in `OllamaChat.Model`:

| Config Value | Actual Claude Model | Best For |
|---|---|---|
| `claude-sonnet` | Claude Sonnet 4 | **Recommended** — best quality/cost balance |
| `claude-haiku` | Claude Haiku 4 | Fastest & cheapest, great for casual chatter |
| `claude-opus` | Claude Opus 4 | Most capable, best roleplay quality |
| `claude-3-5-sonnet` | Claude 3.5 Sonnet | Previous gen, still solid |
| `claude-3-5-haiku` | Claude 3.5 Haiku | Previous gen, budget option |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Fallback model if name not recognized |
| `ANTHROPIC_MAX_TOKENS` | `512` | Max response tokens (keep low for chat) |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1/messages` | API endpoint URL |
| `PROXY_HOST` | `0.0.0.0` | Bind address |
| `PROXY_PORT` | `11435` | Port (11435 avoids conflict with Ollama's 11434) |
| `LOG_LEVEL` | `INFO` | Logging: DEBUG, INFO, WARNING, ERROR |

## Included Extras

### Optimized Prompt Templates

The repo includes Claude-optimized prompt templates for mod-ollama-chat. These take advantage of Claude's superior instruction-following to create immersive bot personalities:

- Bots think they're real players, not NPCs
- Strong class rivalries and faction loyalty
- Natural WoW slang (BiS, oom, pug, ninja, kek)
- Personality-driven reactions to events


### Personality Packs

This repo includes personality SQL packs by Dustin Hendrickson:

- **60 unique personalities** spanning WoW player archetypes and general personality types
- Ready to import into HeidiSQL or your MySQL client
- Compatible with mod-ollama-chat's personality system


## Running as a Service

### Linux (systemd)

```bash
sudo cp ollama-claude-proxy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ollama-claude-proxy
sudo systemctl start ollama-claude-proxy
```

> **Note:** Edit the service file first to set your API key and paths.

### Docker

```bash
docker build -t ollama-claude-proxy .
docker run -d \
  -p 11435:11435 \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  --name ollama-claude-proxy \
  ollama-claude-proxy
```

### Windows (Task Scheduler)

Create a batch file `start-proxy.bat`:
```batch
@echo off
set ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE
python C:\path\to\ollama_claude_proxy.py
```

Add it to Task Scheduler to run at startup.

## Cost Management

Claude API usage is billed per token. Tips to manage costs:

- **Use Claude Haiku** for random/ambient chatter (cheapest)
- **Keep `ANTHROPIC_MAX_TOKENS` low** — 40–100 is plenty for chat
- **Reduce reply chances** in your mod-ollama-chat config:
  ```ini
  OllamaChat.PlayerReplyChance = 70
  OllamaChat.BotReplyChance = 5
  OllamaChat.MaxBotsToPick = 1
  OllamaChat.RandomChatterBotCommentChance = 3
  ```
- **Increase random chatter intervals:**
  ```ini
  OllamaChat.MinRandomInterval = 120
  OllamaChat.MaxRandomInterval = 360
  ```

Rough cost estimates per response:
| Model | Cost per Response (~40 tokens out) |
|---|---|
| Claude Haiku | ~$0.001 |
| Claude Sonnet | ~$0.005 |
| Claude Opus | ~$0.02 |

## Testing

```bash
# Health check
curl http://localhost:11435/

# List models
curl http://localhost:11435/api/tags

# Test generate (what mod-ollama-chat uses)
curl -X POST http://localhost:11435/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet",
    "prompt": "You are a level 80 Orc Warrior. A player asks: Hey, where is the auction house? Reply in under 15 words.",
    "stream": false
  }'

# Test chat
curl -X POST http://localhost:11435/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet",
    "messages": [
      {"role": "system", "content": "You are a WoW NPC. Respond in character."},
      {"role": "user", "content": "Where can I find the blacksmith?"}
    ],
    "stream": false
  }'
```

## Troubleshooting

| Problem | Solution |
|---|---|
| Bots don't respond | Check `OllamaChat.Url` points to `http://localhost:11435/api/generate` |
| "ANTHROPIC_API_KEY not set" | Set the key in the same terminal window before running the proxy |
| API key not persisting | On Windows, `set` only lasts for that CMD session. Use a .bat file. |
| Slow responses | Normal — Claude API takes 1–5s. mod-ollama-chat handles this async. |
| Running alongside Ollama | No conflict — proxy uses port 11435, Ollama uses 11434 |
| Can't reach proxy from another machine | Check firewall, and set `PROXY_HOST=0.0.0.0` |

## Requirements

- **Python 3.10+** (uses only stdlib — zero pip installs)
- **Anthropic API key** from [console.anthropic.com](https://console.anthropic.com/)
- **mod-ollama-chat** installed on AzerothCore with Playerbots

## Contributing

Pull requests welcome! Some ideas:

- [ ] Support for other API providers (OpenAI, Google Gemini)
- [ ] Token usage tracking and cost dashboard
- [ ] Rate limiting per bot
- [ ] Response caching for repeated prompts
- [ ] Config file support (instead of env vars only)

## Credits

- [mod-ollama-chat](https://github.com/DustinHendrickson/mod-ollama-chat) by Dustin Hendrickson
- [AzerothCore](https://github.com/azerothcore/azerothcore-wotlk) — the WoW 3.3.5a emulator
- [mod-playerbots](https://github.com/liyunfan1223/mod-playerbots) by liyunfan1223
- [Anthropic Claude API](https://docs.anthropic.com/)

## License

MIT — do whatever you want with it.
