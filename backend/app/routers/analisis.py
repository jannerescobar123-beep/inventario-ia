"""Endpoints de análisis: KPIs, rotación, predicciones, recomendaciones y alertas.

Los análisis aún no implementados devuelven 200 con `estado: "pendiente"`
para que el frontend pueda integrarse desde el día 1 sin errores.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alerta, Producto, Venta
from app.schemas import AlertaOut, KPIsOut, RespuestaAnalisis
from app.services import estadistica

router = APIRouter(prefix="/api", tags=["Análisis"])


@router.get("/kpis", response_model=KPIsOut)
def kpis(db: Session = Depends(get_db)):
    total = db.query(func.coalesce(func.sum(Venta.importe), 0.0)).scalar() or 0.0
    num_ventas = db.query(func.count(Venta.id)).scalar() or 0
    unidades = db.query(func.coalesce(func.sum(Venta.cantidad), 0.0)).scalar() or 0.0
    num_productos = db.query(func.count(Producto.id)).scalar() or 0
    periodo = db.query(func.min(Venta.fecha), func.max(Venta.fecha)).first()

    return KPIsOut(
        ventas_totales=total,
        num_ventas=num_ventas,
        ticket_promedio=(total / num_ventas) if num_ventas else 0.0,
        unidades_vendidas=unidades,
        num_productos=num_productos,
        periodo_inicio=periodo[0],
        periodo_fin=periodo[1],
    )


@router.get("/analisis/rotacion", response_model=RespuestaAnalisis)
def rotacion(
    dias: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
):
    try:
        datos = estadistica.rotacion_productos(db, dias=dias)
        return RespuestaAnalisis(estado="ok", descripcion="", datos=datos)
    except NotImplementedError:
        return RespuestaAnalisis(
            estado="pendiente",
            descripcion=(
                f"Análisis de rotación a {dias} días aún no implementado. "
                "TODO(Persona A): backend/app/services/estadistica.py"
            ),
        )


@router.get("/predicciones/{producto_id}", response_model=RespuestaAnalisis)
def predicciones(
    producto_id: int,
    dias: Literal[7, 14, 30] = 7,
    db: Session = Depends(get_db),
):
    try:
        datos = estadistica.predecir_demanda(db, producto_id=producto_id, dias=dias)
        return RespuestaAnalisis(estado="ok", descripcion="", datos=datos)
    except NotImplementedError:
        return RespuestaAnalisis(
            estado="pendiente",
            descripcion=(
                f"Predicción de demanda a {dias} días aún no implementada. "
                "TODO(Persona A): backend/app/services/estadistica.py"
            ),
        )


@router.get("/recomendaciones/compra", response_model=RespuestaAnalisis)
def recomendaciones(db: Session = Depends(get_db)):
    try:
        datos = estadistica.recomendaciones_compra(db)
        return RespuestaAnalisis(estado="ok", descripcion="", datos=datos)
    except NotImplementedError:
        return RespuestaAnalisis(
            estado="pendiente",
            descripcion=(
                "Lista de compra sugerida aún no implementada. "
                "TODO(Persona A): backend/app/services/estadistica.py"
            ),
        )


@router.get("/alertas", response_model=list[AlertaOut])
def alertas(db: Session = Depends(get_db)):
    return db.query(Alerta).order_by(Alerta.fecha.desc()).limit(100).all()
