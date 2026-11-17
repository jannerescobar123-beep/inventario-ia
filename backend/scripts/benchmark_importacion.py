"""
Benchmark de importación de ventas (RNF-47).

Mide el tiempo real del importador con 10.000 filas en tres casos:

1. CSV de 10.000 filas sobre base vacía.
2. Excel (.xlsx) de 10.000 filas sobre base vacía.
3. Reimportación del mismo CSV: todas las filas son duplicadas, que es el
   peor caso del camino de deduplicación (RF-05).

Cada medición usa una base de datos temporal que se crea y se destruye
dentro del propio script. La base del demo (backend/datos/inventario.db)
no se abre: se compara su hash SHA-256 antes y después como prueba de que
no se ha tocado.

Ejecución desde la raíz del repositorio:
    backend/.venv/Scripts/python.exe backend/scripts/benchmark_importacion.py
"""
from __future__ import annotations

import csv
import hashlib
import shutil
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402

import backend.api.database as database  # noqa: E402
from backend.api import importador  # noqa: E402

# --- Parámetros del benchmark ---------------------------------------------

FILAS = 10_000
LIMITE_SEGUNDOS = 30.0      # RNF-47: menos de 30 s
PRODUCTOS = 40              # catálogo pequeño y realista
DIAS = 250                  # 40 productos x 250 días = 10.000 combinaciones
INICIO = date(2025, 12, 1)  # así no hay dos filas idénticas en el archivo

BD_DEMO = RAIZ / "backend" / "datos" / "inventario.db"


def _filas_venta() -> List[Dict[str, Any]]:
    """
    Generar 10.000 ventas sin duplicados dentro del archivo.

    Cada fila es única por la pareja (producto, día): no hay dos iguales, así
    que el primer caso mide 10.000 inserciones reales y el tercero mide
    10.000 omisiones.
    """
    filas: List[Dict[str, Any]] = []
    for i in range(FILAS):
        producto = f"Producto {i % PRODUCTOS:02d} repuesto"
        dia = INICIO + timedelta(days=(i // PRODUCTOS) % DIAS)
        filas.append({
            "fecha": dia.isoformat(),
            "producto": producto,
            "cantidad": (i % 4) + 1,
            "precio": round(1_000 + (i % 7) * 250.5, 2),
        })
    return filas


def _escribir_csv(ruta: Path, filas: List[Dict[str, Any]]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as fichero:
        escritor = csv.DictWriter(
            fichero, fieldnames=["fecha", "producto", "cantidad", "precio"]
        )
        escritor.writeheader()
        escritor.writerows(filas)


def _escribir_xlsx(ruta: Path, filas: List[Dict[str, Any]]) -> None:
    pd.DataFrame(filas).to_excel(ruta, sheet_name="ventas", index=False)


def _bd_temporal(carpeta: Path) -> Path:
    """Apuntar el importador a una base nueva y crear el esquema."""
    destino = carpeta / "benchmark.db"
    database.DB_PATH = destino
    database.init_db()
    return destino


def _medir(ruta_archivo: Path) -> Tuple[float, Dict[str, Any]]:
    """Importar el archivo sobre una base vacía y devolver tiempo y resumen."""
    with tempfile.TemporaryDirectory() as temporal:
        _bd_temporal(Path(temporal))
        inicio = time.perf_counter()
        resultado = importador.importar_archivo(str(ruta_archivo))
        segundos = time.perf_counter() - inicio
    return segundos, resultado


def _medir_reimportacion(ruta_archivo: Path) -> Tuple[float, Dict[str, Any]]:
    """Importar dos veces: se mide la segunda, donde todo es duplicado."""
    with tempfile.TemporaryDirectory() as temporal:
        _bd_temporal(Path(temporal))
        importador.importar_archivo(str(ruta_archivo))
        inicio = time.perf_counter()
        resultado = importador.importar_archivo(str(ruta_archivo))
        segundos = time.perf_counter() - inicio
    return segundos, resultado


def _hash(ruta: Path) -> str:
    if not ruta.exists():
        return "(no existe)"
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _linea(etiqueta: str, segundos: float, detalle: str) -> str:
    veredicto = "OK  " if segundos < LIMITE_SEGUNDOS else "LENTO"
    return f"{etiqueta:<38} {segundos:>6.2f} s   [{veredicto}]   {detalle}"


def main() -> int:
    ruta_python_original = database.DB_PATH
    hash_antes = _hash(BD_DEMO)

    filas = _filas_venta()
    print(f"RNF-47 — importación de {len(filas):,} filas (límite {LIMITE_SEGUNDOS:.0f} s)")
    print(f"Python {sys.version.split()[0]} · pandas {pd.__version__}")
    print("-" * 78)

    resultados: List[Tuple[str, float]] = []

    try:
        # mkdtemp en lugar de TemporaryDirectory: en Windows el .xlsx puede
        # seguir abierto (pd.ExcelFile no se cierra en importador), y el
        # borrado automático fallaba con PermissionError tras medir.
        carpeta = Path(tempfile.mkdtemp(prefix="bench_import_"))
        csv_ruta = carpeta / "ventas_10000.csv"
        xlsx_ruta = carpeta / "ventas_10000.xlsx"
        _escribir_csv(csv_ruta, filas)
        _escribir_xlsx(xlsx_ruta, filas)

        segundos_csv, res_csv = _medir(csv_ruta)
        resultados.append(("CSV", segundos_csv))
        print(_linea(
            "1. CSV 10.000 filas", segundos_csv,
            f"{res_csv['total_ventas']:,} guardadas, "
            f"{res_csv['productos_creados']} productos nuevos, "
            f"{len(res_csv['errores'])} errores",
        ))

        segundos_xlsx, res_xlsx = _medir(xlsx_ruta)
        resultados.append(("XLSX", segundos_xlsx))
        print(_linea(
            "2. Excel 10.000 filas", segundos_xlsx,
            f"{res_xlsx['total_ventas']:,} guardadas, "
            f"{res_xlsx['productos_creados']} productos nuevos, "
            f"{len(res_xlsx['errores'])} errores",
        ))

        segundos_dup, res_dup = _medir_reimportacion(csv_ruta)
        resultados.append(("Reimportación", segundos_dup))
        print(_linea(
            "3. Reimportar el mismo CSV", segundos_dup,
            f"{res_dup['total_ventas']:,} nuevas, "
            f"{res_dup['ventas_duplicadas_omitidas']:,} omitidas",
        ))
    finally:
        database.DB_PATH = ruta_python_original
        shutil.rmtree(carpeta, ignore_errors=True)

    print("-" * 78)
    peor = max(segundos for _, segundos in resultados)
    print(f"Peor caso: {peor:.2f} s · margen frente al límite: "
          f"{LIMITE_SEGUNDOS - peor:.2f} s")

    hash_despues = _hash(BD_DEMO)
    iguales = hash_antes == hash_despues
    print(f"Base del demo intacta: {'sí' if iguales else 'NO'} "
          f"({hash_antes[:16]}…)")

    return 0 if iguales and peor < LIMITE_SEGUNDOS else 1


if __name__ == "__main__":
    raise SystemExit(main())
