#!/usr/bin/env bash
# Inventario-IA: levanta Ollama (si hace falta), backend (:8000) y frontend (:5173).
# Uso: ./start.sh   (Ctrl+C detiene backend y frontend)
set -e

BACKEND_PORT=8000
FRONTEND_PORT=5173
VENV=".venv"
PYTHON_VENV="backend/${VENV}/bin/python"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:1.7b}"

echo "🏪 Inventario-IA — modo desarrollo"
echo "   Backend  → http://localhost:${BACKEND_PORT}/docs"
echo "   Frontend → http://localhost:${FRONTEND_PORT}"

# --- 1) Entorno virtual del backend -----------------------------------------
if [ ! -f "${PYTHON_VENV}" ]; then
  echo "📦 Creando entorno virtual del backend..."
  python3 -m venv "backend/${VENV}"
  "${PYTHON_VENV}" -m pip install -q -r requirements.txt
fi

# --- 2) Dependencias del frontend -------------------------------------------
if [ ! -d frontend/node_modules ]; then
  echo "📦 Instalando dependencias del frontend (primera vez)..."
  (cd frontend && npm install)
fi

# --- 3) Ollama: verificar que responda y que el modelo exista ---------------
if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  if command -v ollama >/dev/null 2>&1; then
    echo "🤖 Arrancando Ollama..."
    ollama serve >/dev/null 2>&1 &
    OLLAMA_PID=$!
    sleep 2
  else
    echo "⚠️  Ollama no está instalado: el chat no funcionará (el resto sí)."
    echo "    Instálalo en https://ollama.com y ejecuta: ollama pull ${OLLAMA_MODEL}"
  fi
fi

if command -v ollama >/dev/null 2>&1; then
  if ! ollama list 2>/dev/null | grep -q "^${OLLAMA_MODEL}"; then
    echo "⬇️  Descargando el modelo ${OLLAMA_MODEL} (1,4 GB, solo la primera vez)..."
    ollama pull "${OLLAMA_MODEL}" || echo "⚠️  No se pudo descargar el modelo; el chat fallará."
  fi
fi

# --- 4) Backend + frontend (se detienen con Ctrl+C) -------------------------
cleanup() {
  echo ""
  echo "🛑 Deteniendo backend y frontend..."
  kill 0 2>/dev/null || true
}
trap cleanup INT TERM EXIT

(
  exec "${PYTHON_VENV}" -m uvicorn backend.api.main:app \
    --host 127.0.0.1 --port "${BACKEND_PORT}" --reload
) &

(
  cd frontend
  exec npm run dev -- --port "${FRONTEND_PORT}"
) &

wait
