"""Servicio de importación: Excel/CSV → SQLite.

Convención de archivo (ADR-003 en inventario-ia-docs):
- Hoja "ventas" (obligatoria): fecha, producto/sku, cantidad, precio.
- Hoja "productos" (opcional): sku, producto, categoria, costo, precio_venta,
  stock_inicial (stock físico actual), stock_minimo → catálogo completo.

Los productos se emparejan primero por SKU y, si no hay coincidencia,
por nombre. El stock importado es el conteo físico actual: NO se descuentan
las ventas históricas (esas ya ocurrieron; RF-08 aplica a ventas futuras).
"""
import re
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Importacion, Producto, Venta
from app.schemas import ResumenImportacion

# Formato ISO (2026-05-07): año primero → NO se debe activar dayfirst
_ISO_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}")

ALIAS_SKU = ["sku", "codigo", "código", "codigo de barras", "código de barras", "cod", "cód"]

# Hoja "ventas": nombre canónico → alias aceptados (en minúsculas)
ALIAS_VENTAS = {
    "fecha": ["fecha", "date", "dia", "día"],
    "producto": ["producto", "articulo", "artículo", "descripcion", "descripción", "nombre"],
    "cantidad": ["cantidad", "unidades", "cant", "qty"],
    "precio": ["precio", "precio_unitario", "valor", "monto", "importe"],
}

# Hoja "productos": todos los campos son opcionales menos "producto"
ALIAS_PRODUCTOS = {
    "sku": ALIAS_SKU,
    "producto": ["producto", "articulo", "artículo", "descripcion", "descripción", "nombre"],
    "categoria": ["categoria", "categoría", "familia", "rubro"],
    "costo": ["costo", "cost", "precio_compra"],
    "precio_venta": ["precio_venta", "precio de venta", "precio", "pvp"],
    "stock_inicial": ["stock_inicial", "stock", "inventario", "existencias", "stock_actual"],
    "stock_minimo": ["stock_minimo", "minimo", "mínimo", "stock_min"],
}


def _mapear_columnas(df: pd.DataFrame, alias_map: dict) -> dict[str, str]:
    """Detecta qué columna del DataFrame corresponde a cada campo canónico."""
    normalizadas = {str(col).strip().lower(): col for col in df.columns}
    mapa: dict[str, str] = {}
    for canonico, alias in alias_map.items():
        for alias_nombre in alias:
            if alias_nombre in normalizadas:
                mapa[canonico] = normalizadas[alias_nombre]
                break
    return mapa


def _parsear_fecha(valor) -> date:
    """Interpreta fechas de Excel/CSV sin invertir día y mes.

    - Celda de Excel con fecha real → llega como Timestamp/datetime, se usa tal cual.
    - Texto ISO (2026-05-07) → parseo estándar.
    - Texto latino (07/05/2026) → día primero (dayfirst).
    """
    if hasattr(valor, "date"):
        return pd.to_datetime(valor).date()
    texto = str(valor).strip()
    if _ISO_FECHA.match(texto):
        return pd.to_datetime(texto).date()
    return pd.to_datetime(texto, dayfirst=True).date()


def _numero(valor, defecto: float = 0.0) -> float:
    """Convierte a float de forma tolerante (NaN, texto vacío, '1.234,56' básico)."""
    try:
        resultado = float(str(valor).replace(",", "."))
        return defecto if pd.isna(resultado) else resultado
    except (TypeError, ValueError):
        return defecto


def _texto(valor) -> str:
    """Convierte a texto limpio ('' si es vacío/NaN)."""
    texto = str(valor).strip()
    return "" if texto.lower() == "nan" else texto


# ─────────────────────────────────────────────────────────────────────────────
# Hoja "productos": catálogo + stock actual
# ─────────────────────────────────────────────────────────────────────────────
def importar_hoja_productos(df: pd.DataFrame, db: Session) -> dict:
    """Crea o actualiza productos desde la hoja 'productos' del Excel.

    Empareja por SKU y, si no coincide, por nombre. Devuelve:
        {"creados": int, "actualizados": int, "errores": [...]}
    """
    mapa = _mapear_columnas(df, ALIAS_PRODUCTOS)
    if "producto" not in mapa:
        return {
            "creados": 0,
            "actualizados": 0,
            "errores": [
                "La hoja 'productos' no tiene columna de nombre de producto "
                f"(alias aceptados: {ALIAS_PRODUCTOS['producto']})"
            ],
        }

    creados = 0
    actualizados = 0
    errores: list[str] = []

    for indice, fila in df.iterrows():
        numero_fila = indice + 2
        try:
            nombre = _texto(fila[mapa["producto"]])
            if not nombre:
                raise ValueError("nombre de producto vacío")
            sku = _texto(fila[mapa["sku"]]) if "sku" in mapa else ""

            producto = None
            if sku:
                producto = db.query(Producto).filter(Producto.sku == sku).first()
            if producto is None:
                producto = db.query(Producto).filter(Producto.nombre == nombre).first()

            if producto is None:
                producto = Producto(nombre=nombre, sku=sku or None)
                db.add(producto)
                creados += 1
            else:
                actualizados += 1

            producto.nombre = nombre
            if sku:
                producto.sku = sku
            if "categoria" in mapa and _texto(fila[mapa["categoria"]]):
                producto.categoria = _texto(fila[mapa["categoria"]])
            if "costo" in mapa:
                producto.costo = _numero(fila[mapa["costo"]])
            if "precio_venta" in mapa:
                precio = _numero(fila[mapa["precio_venta"]])
                if precio:
                    producto.precio_venta = precio
            if "stock_inicial" in mapa:
                producto.stock_actual = _numero(fila[mapa["stock_inicial"]])
            if "stock_minimo" in mapa:
                producto.stock_minimo = _numero(fila[mapa["stock_minimo"]])
        except Exception as exc:
            errores.append(f"Hoja productos, fila {numero_fila}: {exc}")

    db.commit()
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:20]}


# ─────────────────────────────────────────────────────────────────────────────
# Hoja "ventas"
# ─────────────────────────────────────────────────────────────────────────────
def importar_dataframe(df: pd.DataFrame, db: Session, nombre_archivo: str) -> ResumenImportacion:
    """Procesa el DataFrame de ventas, lo guarda en SQLite y devuelve el resumen."""
    mapa = _mapear_columnas(df, ALIAS_VENTAS)
    faltantes = [campo for campo in ALIAS_VENTAS if campo not in mapa]

    if faltantes:
        return ResumenImportacion(
            archivo=nombre_archivo,
            mensaje=(
                f"No se encontraron las columnas: {', '.join(faltantes)}. "
                f"Columnas detectadas en el archivo: {', '.join(map(str, df.columns))}. "
                f"Alias aceptados: {ALIAS_VENTAS}"
            ),
        )

    errores: list[str] = []
    filas_ok = 0
    cache_por_sku: dict[str, Producto] = {}
    cache_por_nombre: dict[str, Producto] = {}

    def _obtener_producto(nombre: str, sku: str, precio: float) -> Producto:
        """Busca por SKU, luego por nombre (caché → BD); crea si no existe."""
        producto = cache_por_sku.get(sku) if sku else None
        if producto is None:
            producto = cache_por_nombre.get(nombre)
        if producto is None and sku:
            producto = db.query(Producto).filter(Producto.sku == sku).first()
            if producto:
                cache_por_sku[sku] = producto
        if producto is None:
            producto = db.query(Producto).filter(Producto.nombre == nombre).first()
        if producto is None:
            producto = Producto(nombre=nombre, sku=sku or None, precio_venta=precio)
            db.add(producto)
            db.flush()
        if sku:
            cache_por_sku[sku] = producto
        cache_por_nombre[nombre] = producto
        return producto

    for indice, fila in df.iterrows():
        numero_fila = indice + 2  # +2 por encabezado y base 0
        try:
            fecha = _parsear_fecha(fila[mapa["fecha"]])
            nombre_producto = _texto(fila[mapa["producto"]])
            sku = _texto(fila[mapa["sku"]]) if "sku" in mapa else ""
            cantidad = _numero(fila[mapa["cantidad"]], -1.0)
            precio = _numero(fila[mapa["precio"]])

            if not nombre_producto:
                raise ValueError("nombre de producto vacío")
            if cantidad < 0:
                raise ValueError("cantidad negativa")

            producto = _obtener_producto(nombre_producto, sku, precio)
            db.add(
                Venta(
                    producto_id=producto.id,
                    fecha=fecha,
                    cantidad=cantidad,
                    precio_unitario=precio,
                    importe=cantidad * precio,
                )
            )
            filas_ok += 1
        except Exception as exc:
            errores.append(f"Fila {numero_fila}: {exc}")

    importacion = Importacion(
        archivo=nombre_archivo,
        filas_ok=filas_ok,
        filas_error=len(errores),
        estado="procesada" if filas_ok else "fallida",
        detalle="\n".join(errores[:100]),
    )
    db.add(importacion)
    db.commit()

    return ResumenImportacion(
        archivo=nombre_archivo,
        filas_ok=filas_ok,
        filas_error=len(errores),
        errores=errores[:20],
        importacion_id=importacion.id,
    )
