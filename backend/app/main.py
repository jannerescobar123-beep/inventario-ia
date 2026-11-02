"""API principal de Inventario-IA.

Levantar en desarrollo:
    uvicorn app.main:app --reload --port 8000
Docs interactivas: http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import analisis, chat, importar, productos


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crea las tablas si no existen (para producción real usar migraciones: Alembic)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Inventario-IA",
    version="0.1.0",
    description="Análisis de ventas e inventario con IA local para PyMEs",
    lifespan=lifespan,
)

# El frontend de desarrollo (Vite) corre en otro puerto → CORS abierto en dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (productos.router, importar.router, analisis.router, chat.router):
    app.include_router(router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "app": "inventario-ia"}
