#!/bin/bash
# Patch LiteLLM's websearch_interception handler to report proper search count,
# then start LiteLLM with the passed arguments.
#
# Usage (from docker-compose):
#   command: ["/app/patch_websearch_count.sh", "--config", "/app/litellm-config/config.yaml", ...]

set -e

echo "[startup] Patching websearch count..."
python3 /app/patch_websearch_count.py

echo "[startup] Starting LiteLLM..."
exec /app/.venv/bin/litellm "$@"
