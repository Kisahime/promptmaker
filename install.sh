#!/usr/bin/env bash
# PromptMaker installer for macOS / Linux
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
  echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1
fi
"$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt
command -v ollama >/dev/null && echo "Ollama found. Pull a model once: ollama pull llama3.2" \
  || echo "Optional: install Ollama for AI features: https://ollama.com/download"
echo "Done. Start with ./run.sh"
