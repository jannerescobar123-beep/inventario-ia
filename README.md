# Inventario-IA

MVP de análisis de ventas e inventario con **IA local**. Toda la intelligence artificial se
ejecuta en la máquina del usuario con Ollama; los datos viven en un único archivo SQLite.

- **Backend:** Python + FastAPI + pandas + SQLite (archivo único, sin configuración).
- **Frontend:** React 18 + Vite + Redux + Recharts, sistema de diseño propio en modo oscuro.
- **IA:** Ollama con *function calling*. El modelo **no calcula**: el backend expone 5
  herramientas deterministas sobre SQLite y el LLM solo decide cuál llamar y redacta la respuesta.

La documentación funcional (requisitos, ADRs, dirección visual) vive en el repositorio
`inventario-ia-docs`: <https://github.com/jannerescobar123-beep/inventario-ia-docs>

---

## Requisitos

| Herramienta | Versión | Nota |
|---|---|---|
| Python | 3.15 (probado) | compatível con 3.11+ |
| Node.js | 18+ (probado con v26.6.0) | para Vite 5 |
| Ollama | 0.40.12 | con el modelo `qwen3:1.7b` descargado |

## Instalación

```bash
# Backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

## Arranque

Son **tres procesos** y deben coexistir:

```bash
# 1) IA local
ollama serve

# 2) API (desde la raíz del proyecto)
python -m uvicorn backend.api.main:app --port 8000 --host 127.0.0.1

# 3) Frontend
cd frontend
npm run dev
```

- Frontend: <http://localhost:5173>
- API: <http://127.0.0.1:8000> (`/health` comprueba que responde)

> El primer mensaje del chat tarda ~22 s (carga del modelo en RAM). Los siguientes: 8–11 s.
> El modelo se elige con `OLLAMA_MODEL` (por defecto `qwen3:1.7b`); `OLLAMA_URL` apunta al
> servidor de Ollama (por defecto `http://127.0.0.1:11434`).

## Datos de demostración

La base `backend/datos/inventario.db` **no se versiona**: es un binario generado.

1. Al arrancar, la API crea el esquema vacío (`CREATE TABLE IF NOT EXISTS`).
2. Se puebla importando el Excel de demo:
   - desde la interfaz, en **Importar** (ruta `/importar`), o
   - por API: `POST /api/importar` con `backend/datos/ventas_demo.xlsx`.
3. El Excel de demo se regenera con:
   ```bash
   python backend/scripts/generar_datos_prueba.py
   ```

## API

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/` | identificación del servicio |
| GET | `/health` | estado de la API |
| GET | `/api/kpis` | indicadores de inventario y rotación |
| GET | `/api/alertas` | alertas de agotamiento y comportamiento inusual |
| GET | `/api/productos` | catálogo de productos |
| GET | `/api/rotacion` | rotación por producto |
| GET | `/api/recomendaciones` | recomendaciones de compra |
| POST | `/api/importar` | importa Excel/CSV (`multipart/form-data`) |
| POST | `/api/chat` | pregunta en lenguaje natural con function calling |

Rutas del frontend: `/` (dashboard), `/importar`, `/alertas`, `/compras`, `/chat`.

## Estructura

```
backend/
  api/        main.py (API + chat), database.py, estadisticas.py, importador.py
  datos/      ventas_demo.xlsx, ventas_demo.csv, inventario.db (generado, no versionado)
  scripts/    generar_datos_prueba.py
frontend/
  src/        App.jsx, main.jsx, styles.css, components/, store/, utils/
```

## Notas

- `frontend/package.json` declara `react-bootstrap`, pero **no se usa**: la interfaz usa un
  sistema de diseño propio (`frontend/src/styles.css`). Retirarlo está pendiente.
- No hay CDN ni tipografías externas: todo es local y funciona sin conexión.
