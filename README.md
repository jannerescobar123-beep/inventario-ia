# 🏪 Inventario-IA

Software para tiendas, ferreterías y negocios de barrio (PyMEs) que **importa ventas desde Excel**, las analiza con estadística y usa **IA 100% local** para responder:

- 🛒 ¿Qué productos debo comprar esta semana?
- 📉 ¿Qué productos están vendiendo menos?
- ⏳ ¿Cuáles pueden agotarse pronto?
- 🐢 ¿Qué productos tienen una rotación muy baja?

> 🔒 Los datos nunca salen del negocio: todo corre offline (SQLite + Ollama).

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                  PC del negocio (offline)            │
│                                                     │
│  ┌──────────────┐      ┌───────────────────────┐   │
│  │   FRONTEND   │ HTTP │        BACKEND         │   │
│  │ React+Vite   │─────▶│  FastAPI (Python)      │   │
│  │ Dashboard,   │      │  ├─ Importador Excel   │   │
│  │ alertas,     │      │  ├─ Motor estadístico  │   │
│  │ chat IA      │      │  └─ API REST           │   │
│  └──────────────┘      └───────┬───────────────┘   │
│                                │                    │
│              ┌─────────────────┼──────────────┐    │
│              ▼                 ▼              ▼    │
│        ┌──────────┐    ┌───────────┐   ┌─────────┐ │
│        │  SQLite  │    │  Ollama   │   │ pandas/ │ │
│        │ (1 solo  │    │ LLM local │   │ stats   │ │
│        │ archivo) │    │ Llama 3.2 │   │ models  │ │
│        └──────────┘    └───────────┘   └─────────┘ │
└─────────────────────────────────────────────────────┘
```

## Estructura del repo

```
inventario-ia/
├── backend/            # FastAPI + SQLAlchemy + pandas (Persona A)
│   ├── app/
│   │   ├── main.py         # Punto de entrada de la API
│   │   ├── database.py     # SQLite + sesión SQLAlchemy
│   │   ├── models.py       # Tablas: productos, ventas, alertas...
│   │   ├── schemas.py      # Esquemas Pydantic (contrato API)
│   │   ├── routers/        # Endpoints: productos, importar, análisis, chat
│   │   └── services/       # importador, estadistica, llm
│   └── scripts/
│       └── generar_datos_prueba.py   # Crea datos/ventas_demo.xlsx
├── frontend/           # React + Vite (Persona B)
│   └── src/pages/      # Dashboard, Importar, Chat
├── docs/
│   ├── ARQUITECTURA.md # Decisiones y modelo de datos
│   └── openapi.yaml    # ⭐ Contrato de API acordado entre ambos
├── datos/              # Archivos Excel de prueba (no se versiona)
├── docker-compose.yml  # (Opcional) backend + Ollama
└── start.sh / start.bat
```

## Inicio rápido

```bash
# 1) Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# → API y docs interactivas en http://localhost:8000/docs

# 2) Datos de prueba (otra terminal)
python scripts/generar_datos_prueba.py
# → crea datos/ventas_demo.xlsx (6 meses, ~200 productos, estacionalidad)

# 3) Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173

# 4) IA local
ollama pull llama3.2:3b
ollama serve   # si no está corriendo ya
```

Con Docker (opcional): `docker compose up --build`

## Roles del equipo

| Persona | Responsabilidad |
|---|---|
| **A — Núcleo de datos e inteligencia** | Importador, modelo de datos, motor estadístico, predicciones, recomendaciones, endpoints |
| **B — Producto: UI y Asistente IA** | Dashboard, wizard de importación, panel de alertas, chat con Ollama + function calling |

El detalle del plan está en el repositorio de gestión: **`inventario-ia-docs`**
(requisitos, roadmap semanal, roles, ADRs y plantilla de reuniones).

## Reglas del equipo

1. **El contrato de API (`docs/openapi.yaml`) es la ley.** Cualquier cambio se acuerda y se registra como ADR el mismo día.
2. Los `TODO(Persona A)` y `TODO(Persona B)` marcan el trabajo pendiente del prototipo.
3. Commits pequeños con formato `feat|fix|docs: descripción`.
