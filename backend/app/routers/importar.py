"""Endpoint de importación de Excel/CSV de ventas.

Flujo: el usuario sube el archivo → se guarda en datos/uploads → el servicio
`importador` procesa las hojas ("productos" si existe, luego "ventas")
y devuelve un resumen con errores por fila.
"""
import io
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ResumenImportacion
from app.services.importador import importar_dataframe, importar_hoja_productos

router = APIRouter(prefix="/api/importar", tags=["Importación"])

EXTENSIONES_OK = {".xlsx", ".xls", ".csv"}
UPLOADS_DIR = Path("datos/uploads")


@router.post("", response_model=ResumenImportacion)
async def importar(archivo: UploadFile, db: Session = Depends(get_db)):
    nombre = archivo.filename or "sin_nombre"
    extension = Path(nombre).suffix.lower()

    if extension not in EXTENSIONES_OK:
        raise HTTPException(
            status_code=400,
            detail=f"Formato '{extension}' no soportado. Use: {', '.join(sorted(EXTENSIONES_OK))}",
        )

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    # Guardamos una copia del archivo original (historial de importaciones)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    destino = UPLOADS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{nombre}"
    destino.write_bytes(contenido)

    # Lectura: CSV → una sola hoja de ventas. Excel → hoja "ventas" (o la
    # primera) + hoja opcional "productos" (ADR-003).
    try:
        import pandas as pd

        if extension == ".csv":
            df_ventas = pd.read_csv(io.BytesIO(contenido), sep=None, engine="python")
            df_productos = None
        else:
            libro = pd.ExcelFile(io.BytesIO(contenido))
            hojas = {hoja.strip().lower(): hoja for hoja in libro.sheet_names}
            df_ventas = libro.parse(hojas.get("ventas", libro.sheet_names[0]))
            df_productos = libro.parse(hojas["productos"]) if "productos" in hojas else None
    except Exception as exc:  # archivo corrupto, .xls antiguo sin xlrd, etc.
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo leer el archivo: {exc}",
        ) from exc

    # 1) Catálogo primero (si existe la hoja) → productos con stock/costos
    productos_creados = 0
    productos_actualizados = 0
    if df_productos is not None:
        resumen_catalogo = importar_hoja_productos(df_productos, db)
        productos_creados = resumen_catalogo["creados"]
        productos_actualizados = resumen_catalogo["actualizados"]

    # 2) Ventas después → se emparejan con el catálogo por SKU/nombre
    resumen = importar_dataframe(df_ventas, db, nombre_archivo=nombre)
    resumen.productos_creados = productos_creados
    resumen.productos_actualizados = productos_actualizados

    if df_productos is not None and (productos_creados or productos_actualizados):
        resumen.mensaje = (
            f"Catálogo: {productos_creados} productos creados, "
            f"{productos_actualizados} actualizados. "
            f"Ventas: {resumen.filas_ok} filas importadas."
        )

    return resumen
