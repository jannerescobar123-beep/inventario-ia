#!/usr/bin/env bash
# Inventario-IA: levanta backend (:8000) y frontend (:5173) en modo desarrollo.
set -e

echo "🏪 Inventario-IA — modo desarrollo"
echo "   Backend  → http://localhost:8000/docs"
echo "   Frontend → http://localhost:5173"

(
  cd backend
  if [ ! -d .venv ]; then
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q -r requirements.txt
  else
    source .venv/bin/activate
  fi
  uvicorn app.main:app --reload --port 8000
) &

(
  cd frontend
  npm install
  npm run dev
) &

wait
