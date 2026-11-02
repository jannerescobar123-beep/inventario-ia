@echo off
REM Inventario-IA: levanta backend (:8000) y frontend (:5173) en Windows.
echo 🏪 Inventario-IA - modo desarrollo
echo    Backend  -^> http://localhost:8000/docs
echo    Frontend -^> http://localhost:5173

start "inventario-ia-backend" cmd /k "cd backend && (if not exist .venv python -m venv .venv) && .venv\Scripts\activate && pip install -q -r requirements.txt && uvicorn app.main:app --reload --port 8000"

start "inventario-ia-frontend" cmd /k "cd frontend && npm install && npm run dev"
