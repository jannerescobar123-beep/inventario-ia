"""Modelos ORM del sistema (fuente de verdad: docs/ARQUITECTURA.md)."""
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text

from app.database import Base


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True, index=True, nullable=True)
    nombre = Column(String(200), nullable=False, index=True)
    categoria = Column(String(100), default="General")
    unidad = Column(String(20), default="unidad")
    costo = Column(Float, default=0.0)
    precio_venta = Column(Float, default=0.0)
    stock_actual = Column(Float, default=0.0)
    stock_minimo = Column(Float, default=0.0)
    activo = Column(Boolean, default=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=True)


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    fecha = Column(Date, nullable=False, index=True)
    cantidad = Column(Float, nullable=False)
    precio_unitario = Column(Float, default=0.0)
    importe = Column(Float, default=0.0)


class Proveedor(Base):
    __tablename__ = "proveedores"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(200), nullable=False)
    lead_time_dias = Column(Integer, default=7)


class Importacion(Base):
    __tablename__ = "importaciones"

    id = Column(Integer, primary_key=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    archivo = Column(String(300))
    filas_ok = Column(Integer, default=0)
    filas_error = Column(Integer, default=0)
    estado = Column(String(20), default="procesada")  # procesada | fallida
    detalle = Column(Text, nullable=True)


class Alerta(Base):
    __tablename__ = "alertas"

    id = Column(Integer, primary_key=True)
    tipo = Column(String(50))  # riesgo_agotamiento | baja_rotacion | anomalia_ventas
    severidad = Column(String(10), default="media")  # critica | media | baja
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=True)
    mensaje = Column(Text, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    leida = Column(Boolean, default=False)


# Referencia para evitar warnings de imports no usados en type hints futuros
_ = (date,)
