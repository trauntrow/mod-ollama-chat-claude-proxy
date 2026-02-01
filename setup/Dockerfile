FROM python:3.12-slim

LABEL maintainer="ollama-claude-proxy"
LABEL description="Ollama API proxy that forwards requests to Anthropic Claude"

WORKDIR /app
COPY ollama_claude_proxy.py .

EXPOSE 11435

ENV PROXY_HOST=0.0.0.0
ENV PROXY_PORT=11435
ENV ANTHROPIC_MAX_TOKENS=512
ENV LOG_LEVEL=INFO

CMD ["python", "ollama_claude_proxy.py"]
