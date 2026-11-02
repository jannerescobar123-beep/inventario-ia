"""Servicio de importación: Excel/CSV → SQLite.

Acepta variantes de nombres de columnas (fecha/date/día, producto/artículo,
cantidad/unidades, precio/valor) y reporta errores fila por fila sin
detener toda la carga.
"""
import pandas as pd
from sqlalchemy.orm import Session

from app.models import Importacion, Producto, Venta
from app.schemas import ResumenImportacion

# nombre canónico → alias aceptados (en minúsculas, sin espacios)
ALIAS_COLUMNAS = {
    "fecha": ["fecha", "date", "dia", "día"],
    "producto": ["producto", "articulo", "artículo", "descripcion", "descripción", "nombre"],
    "cantidad": ["cantidad", "unidades", "cant", "qty"],
    "precio": ["precio", "precio_unitario", "valor", "monto", "importe"],
}


def _mapear_columnas(df: pd.DataFrame) -> dict[str, str]:
    """Detecta qué columna del DataFrame corresponde a cada campo canónico."""
    mapa: dict[str, str] = {}
    normalizadas = {str(col).strip().lower(): col for col in df.columns}
    for canonico, alias in ALIAS_COLUMNAS.items():
        for alias_nombre in alias:
            if alias_nombre in normalizadas:
                mapa[canonico] = normalizadas[alias_nombre]
                break
    return mapa


def importar_dataframe(df: pd.DataFrame, db: Session, nombre_archivo: str) -> ResumenImportacion:
    """Procesa el DataFrame de ventas, lo guarda en SQLite y devuelve el resumen."""
    mapa = _mapear_columnas(df)
    faltantes = [campo for campo in ALIAS_COLUMNAS if campo not in mapa]

    if faltantes:
        return ResumenImportacion(
            archivo=nombre_archivo,
            mensaje=(
                f"No se encontraron las columnas: {', '.join(faltantes)}. "
                f"Columnas detectadas en el archivo: {', '.join(map(str, df.columns))}. "
                f"Alias aceptados: {ALIAS_COLUMNAS}"
            ),
        )

    errores: list[str] = []
    filas_ok = 0
    cache_productos: dict[str, Producto] = {}

    for indice, fila in df.iterrows():
        numero_fila = indice + 2  # +2 por encabezado y base 0
        try:
            fecha = pd.to_datetime(fila[mapa["fecha"]], dayfirst=True).date()
            nombre_producto = str(fila[mapa["producto"]]).strip()
            cantidad = float(fila[mapa["cantidad"]])
            precio = float(fila[mapa["precio"]] or 0)

            if not nombre_producto or nombre_producto.lower() == "nan":
                raise ValueError("nombre de producto vacío")
            if cantidad < 0:
                raise ValueError("cantidad negativa")

            producto = cache_productos.get(nombre_producto)
            if producto is None:
                producto = (
                    db.query(Producto).filter(Producto.nombre == nombre_producto).first()
                )
                if producto is None:
                    producto = Producto(nombre=nombre_producto, precio_venta=precio)
                    db.add(producto)
                    db.flush()  # obtiene producto.id sin cerrar la transacción
                cache_productos[nombre_producto] = producto

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
