@echo off
REM Inventario-IA: levanta backend (:8000) y frontend (:5173) en Windows.
REM Uso: doble clic en start.bat (cada servicio en su ventana; cerrarlas para parar).
setlocal
cd /d "%~dp0"

set BACKEND_PORT=8000
set FRONTEND_PORT=5173
set VENV=backend\.venv

echo 🏪 Inventario-IA - modo desarrollo
echo    Backend  -^> http://localhost:%BACKEND_PORT%/docs
echo    Frontend -^> http://localhost:%FRONTEND_PORT%
echo.
echo NOTA: el chat necesita Ollama corriendo con el modelo qwen3:1.7b
echo       (https://ollama.com  ^&  ollama pull qwen3:1.7b)
echo.

REM --- Dependencias del backend (solo la primera vez) ------------------------
if not exist "%VENV%\Scripts\python.exe" (
  echo 📦 Creando entorno virtual del backend...
  python -m venv %VENV%
  "%VENV%\Scripts\python.exe" -m pip install -q -r requirements.txt
)

REM --- Dependencias del frontend (solo la primera vez) -----------------------
if not exist "frontend\node_modules" (
  echo 📦 Instalando dependencias del frontend...
  pushd frontend
  call npm install
  popd
)

REM --- Backend (ventana 1) ----------------------------------------------------
start "inventario-ia-backend" cmd /k "cd /d %~dp0 && %VENV%\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload"

REM --- Frontend (ventana 2) ---------------------------------------------------
start "inventario-ia-frontend" cmd /k "cd /d %~dp0frontend && npm run dev -- --port %FRONTEND_PORT%"

echo Listo. Abre http://localhost:%FRONTEND_PORT% en el navegador.
timeout /t 5 >nul
