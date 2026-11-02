"""Endpoint de importación de Excel/CSV de ventas.

Flujo: el usuario sube el archivo → se guarda en datos/uploads → el servicio
`importador` lo procesa con pandas y devuelve un resumen con errores por fila.
"""
import io
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ResumenImportacion
from app.services.importador import importar_dataframe

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

    # Pandas lee desde memoria (soporta Excel y CSV)
    try:
        import pandas as pd

        if extension == ".csv":
            df = pd.read_csv(io.BytesIO(contenido), sep=None, engine="python")
        else:
            df = pd.read_excel(io.BytesIO(contenido))
    except Exception as exc:  # archivo corrupto, .xls antiguo sin xlrd, etc.
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo leer el archivo: {exc}",
        ) from exc

    return importar_dataframe(df, db, nombre_archivo=nombre)
