"""
Pruebas de RF-05 (importación incremental sin duplicar) y RF-07 (alta y
edición manual de productos).

Igual que test_smoke.py, trabajan sobre una base de datos temporal: nunca
tocan backend/datos/inventario.db.

Ejecución desde la raíz del repositorio:
    backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v
"""
import sys
from pathlib import Path

import pytest

# La raíz del repositorio en el path para importar backend.* como paquete
RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fastapi.testclient import TestClient  # noqa: E402

import backend.api.database as database  # noqa: E402
from backend.api.database import normalizar_texto  # noqa: E402


@pytest.fixture()
def bd_temporal(tmp_path, monkeypatch):
    """BD temporal con un producto sembrado (Martillo profesional)."""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_rf05_rf07.db")
    database.init_db()

    conn = database.get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO productos
               (sku, nombre, nombre_norm, categoria, unidad, costo,
                precio_venta, stock_actual, stock_minimo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "MART-001",
                "Martillo profesional",
                normalizar_texto("Martillo profesional"),
                "Herramientas",
                "unidad",
                25.0,
                44.0,
                10,
                5,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return database.DB_PATH


@pytest.fixture()
def client(bd_temporal):
    from backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client


def _escribir_csv(ruta: Path, filas: str) -> str:
    """Escribir un CSV de ventas y devolver su ruta como texto."""
    ruta.write_text("fecha,producto,cantidad,precio\n" + filas, encoding="utf-8")
    return str(ruta)


def _contar_ventas() -> int:
    conn = database.get_db()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0])
    finally:
        conn.close()


# --- RF-07: alta manual ----------------------------------------------------

def test_crear_producto(client):
    r = client.post("/api/productos", json={
        "nombre": "Destornillador plano",
        "sku": "DEST-001",
        "categoria": "Herramientas",
        "unidad": "unidad",
        "costo": 3.5,
        "precio_venta": 7.0,
        "stock_actual": 12,
        "stock_minimo": 4,
    })

    assert r.status_code == 201, r.text
    producto = r.json()
    assert producto["nombre"] == "Destornillador plano"
    assert producto["sku"] == "DEST-001"
    assert producto["unidad"] == "unidad"
    assert producto["stock_actual"] == 12
    assert producto["nombre_norm"] == normalizar_texto("Destornillador plano")

    catalogo = client.get("/api/productos").json()
    assert any(p["sku"] == "DEST-001" for p in catalogo)


def test_crear_producto_sin_sku_genera_uno(client):
    r = client.post("/api/productos", json={"nombre": "Cinta metrica 5m"})

    assert r.status_code == 201, r.text
    assert r.json()["sku"]


def test_crear_producto_con_sku_repetido_da_409(client):
    r = client.post("/api/productos", json={
        "nombre": "Otro martillo",
        "sku": "MART-001",
    })

    assert r.status_code == 409
    assert "MART-001" in r.json()["detail"]


def test_crear_producto_sin_nombre_da_422(client):
    r = client.post("/api/productos", json={"nombre": ""})
    assert r.status_code == 422


def test_crear_producto_con_stock_negativo_da_422(client):
    r = client.post("/api/productos", json={"nombre": "Prueba", "stock_actual": -1})
    assert r.status_code == 422


# --- RF-07: edición manual -------------------------------------------------

def test_editar_producto(client):
    creado = client.post("/api/productos", json={
        "nombre": "Llave inglesa",
        "sku": "LLAV-001",
        "costo": 8.0,
        "precio_venta": 15.0,
        "stock_actual": 3,
    }).json()

    r = client.put(f"/api/productos/{creado['id']}", json={
        "nombre": "Llave inglesa ajustable",
        "sku": "LLAV-001",
        "categoria": "Herramientas",
        "unidad": "unidad",
        "costo": 9.0,
        "precio_venta": 18.0,
        "stock_actual": 6,
        "stock_minimo": 2,
    })

    assert r.status_code == 200, r.text
    editado = r.json()
    assert editado["nombre"] == "Llave inglesa ajustable"
    assert editado["precio_venta"] == 18.0
    assert editado["stock_actual"] == 6
    assert editado["nombre_norm"] == normalizar_texto("Llave inglesa ajustable")


def test_editar_producto_inexistente_da_404(client):
    r = client.put("/api/productos/9999", json={"nombre": "Fantasma"})
    assert r.status_code == 404


def test_editar_con_sku_de_otro_producto_da_409(client):
    primero = client.post("/api/productos", json={
        "nombre": "Sierra", "sku": "SIER-001",
    }).json()
    segundo = client.post("/api/productos", json={
        "nombre": "Serrucho", "sku": "SERR-001",
    }).json()

    r = client.put(f"/api/productos/{segundo['id']}", json={
        "nombre": "Serrucho", "sku": primero["sku"],
    })

    assert r.status_code == 409


# --- RF-05: importación incremental sin duplicar ---------------------------

def test_reimportar_el_mismo_archivo_no_duplica(bd_temporal, tmp_path):
    from backend.api import importador

    csv = _escribir_csv(tmp_path / "ventas.csv", (
        "2026-11-01,Martillo profesional,2,44.0\n"
        "2026-11-02,Martillo profesional,1,44.0\n"
        "2026-11-01,Tornillo metrico 12mm,5,1.2\n"
    ))

    primera = importador.importar_csv(csv)
    assert primera["total_ventas"] == 3
    assert primera["ventas_duplicadas_omitidas"] == 0
    assert _contar_ventas() == 3

    segunda = importador.importar_csv(csv)
    assert segunda["total_ventas"] == 0
    assert segunda["ventas_duplicadas_omitidas"] == 3
    assert _contar_ventas() == 3, "reimportar no debe crear ventas nuevas"


def test_importacion_increcional_guarda_solo_lo_nuevo(bd_temporal, tmp_path):
    """Un archivo con 3 filas idénticas y otro con 5: la BD acaba con 5."""
    from backend.api import importador

    fila = "2026-11-03,Martillo profesional,4,44.0\n"

    primero = importador.importar_csv(
        _escribir_csv(tmp_path / "dia1.csv", fila * 3)
    )
    assert primero["total_ventas"] == 3
    assert _contar_ventas() == 3

    segundo = importador.importar_csv(
        _escribir_csv(tmp_path / "dia2.csv", fila * 5)
    )
    assert segundo["total_ventas"] == 2, "solo las 2 ventas que faltaban"
    assert segundo["ventas_duplicadas_omitidas"] == 3
    assert _contar_ventas() == 5


def test_venta_distinta_no_se_confunde_con_duplicado(bd_temporal, tmp_path):
    """Misma fecha y producto, distinta cantidad: son ventas distintas."""
    from backend.api import importador

    csv = _escribir_csv(tmp_path / "ventas.csv", (
        "2026-11-04,Martillo profesional,1,44.0\n"
        "2026-11-04,Martillo profesional,2,44.0\n"
        "2026-11-04,Martillo profesional,1,40.0\n"
    ))

    resultado = importador.importar_csv(csv)

    assert resultado["total_ventas"] == 3
    assert resultado["ventas_duplicadas_omitidas"] == 0
    assert _contar_ventas() == 3
