"""Esquemas Pydantic: el contrato de respuesta de la API (ver docs/openapi.yaml)."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProductoNuevo(BaseModel):
    sku: Optional[str] = None
    nombre: str
    categoria: str = "General"
    unidad: str = "unidad"
    costo: float = 0.0
    precio_venta: float = 0.0
    stock_actual: float = 0.0
    stock_minimo: float = 0.0


class ProductoOut(ProductoNuevo):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool = True


class ResumenImportacion(BaseModel):
    archivo: str
    filas_ok: int = 0
    filas_error: int = 0
    errores: list[str] = []
    importacion_id: Optional[int] = None
    mensaje: Optional[str] = None
    productos_creados: int = 0
    productos_actualizados: int = 0


class AlertaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    severidad: str
    producto_id: Optional[int] = None
    mensaje: str
    fecha: datetime
    leida: bool


class ChatRequest(BaseModel):
    pregunta: str


class ChatResponse(BaseModel):
    respuesta: str
    modelo: Optional[str] = None
    conectado: bool = False


class KPIsOut(BaseModel):
    ventas_totales: float = 0.0
    num_ventas: int = 0
    ticket_promedio: float = 0.0
    unidades_vendidas: float = 0.0
    num_productos: int = 0
    periodo_inicio: Optional[date] = None
    periodo_fin: Optional[date] = None


class RespuestaAnalisis(BaseModel):
    """Respuesta genérica para endpoints de análisis aún no implementados."""

    estado: str = "pendiente"  # pendiente | ok
    descripcion: str = ""
    datos: Optional[dict] = None
