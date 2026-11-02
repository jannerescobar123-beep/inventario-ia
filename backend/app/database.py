"""Configuración de base de datos (SQLite, un solo archivo, cero configuración)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./inventario.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # necesario para SQLite + FastAPI
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Base para todos los modelos ORM."""


def get_db():
    """Dependencia de FastAPI que entrega una sesión de BD por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
