#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/7] Python compile checks"
python3 -m py_compile \
  api.py main.py observer.py reasoner.py agent_loops.py datasource.py auth.py database.py cli.py

echo "[2/7] Backend tests"
if [[ -x ".venv/bin/python" ]]; then
  .venv/bin/python -m pytest -q
else
  python3 -m pytest -q
fi

echo "[3/7] Frontend lint"
(
  cd frontend
  npm run lint
)

echo "[4/7] Frontend build"
(
  cd frontend
  npx vite build --outDir /tmp/perceptix-frontend-build-hackathon
)

echo "[5/7] Gemini configuration"
if [[ -z "${GEMINI_MODEL_NAME:-}" ]]; then
  echo "WARN: GEMINI_MODEL_NAME is not set. Default model is models/gemini-3-pro-preview."
  echo "INFO: Set GEMINI_MODEL_NAME explicitly if you want to use a different Gemini model."
else
  echo "INFO: GEMINI_MODEL_NAME=${GEMINI_MODEL_NAME}"
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "WARN: GEMINI_API_KEY is not set. Reasoner will run in mock mode."
else
  echo "INFO: GEMINI_API_KEY is set."
fi

echo "[6/7] Live Gemini proof endpoint (if API running)"
if curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; then
  curl -fsS "http://localhost:8000/api/v1/hackathon/gemini-proof"
  echo
else
  echo "INFO: API is not running on localhost:8000. Skipping live endpoint check."
fi

echo "[7/7] Hackathon preflight complete"
