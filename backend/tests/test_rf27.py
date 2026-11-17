"""
Pruebas de RF-27: órdenes de compra exportables e imprimibles.

Trabajan sobre una base de datos temporal: nunca tocan
backend/datos/inventario.db.

Ejecución desde la raíz del repositorio:
    backend/.venv/Scripts/python.exe -m pytest backend/tests/test_rf27.py -v
"""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fastapi.testclient import TestClient  # noqa: E402

import backend.api.database as database  # noqa: E402
from backend.api.database import normalizar_texto  # noqa: E402


def _insertar_producto(nombre, categoria="Herramientas", stock_actual=4,
                       stock_minimo=10, costo=2.5, precio_venta=7.0):
    conn = database.get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO productos
               (sku, nombre, nombre_norm, categoria, unidad, costo,
                precio_venta, stock_actual, stock_minimo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                nombre[:8].upper().replace(" ", ""), nombre,
                normalizar_texto(nombre), categoria, "unidad",
                costo, precio_venta, stock_actual, stock_minimo,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _insertar_ventas(nombre, filas):
    conn = database.get_db()
    try:
        cursor = conn.cursor()
        for fecha, cantidad in filas:
            cursor.execute(
                """INSERT INTO ventas (fecha, producto, producto_norm, cantidad, precio)
                   VALUES (?, ?, ?, ?, ?)""",
                (fecha, nombre, normalizar_texto(nombre), cantidad, 7.0),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def bd_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_rf27.db")
    database.init_db()
    return database.DB_PATH


@pytest.fixture()
def client(bd_temporal):
    from backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def catalogo_con_demanda(bd_temporal):
    """Dos productos que necesitan compra, con ventas que justifican la demanda."""
    _insertar_producto("Cinta métrica 5m", stock_actual=4, stock_minimo=10,
                       costo=2.5)
    _insertar_producto("Brocha 3 pulgadas", categoria="Pintura", stock_actual=1,
                       stock_minimo=8, costo=4.0)
    _insertar_ventas("Cinta métrica 5m", [("2026-11-14", 2), ("2026-11-15", 2)])
    _insertar_ventas("Brocha 3 pulgadas", [("2026-11-14", 3), ("2026-11-15", 1)])
    return bd_temporal


# --- La orden en JSON ------------------------------------------------------

def test_orden_json_tiene_cabecera_lineas_y_totales(client, catalogo_con_demanda):
    respuesta = client.get("/api/ordenes-compra")
    assert respuesta.status_code == 200, respuesta.text
    orden = respuesta.json()

    assert orden["titulo"] == "Orden de compra"
    assert len(orden["fecha_emision"]) == 10  # AAAA-MM-DD
    assert orden["lead_time_dias"] == 7
    assert len(orden["lineas"]) == 2
    assert [linea["num"] for linea in orden["lineas"]] == [1, 2]


def test_totales_suman_unidades_y_coste(client, catalogo_con_demanda):
    orden = client.get("/api/ordenes-compra").json()

    unidades = sum(linea["cantidad"] for linea in orden["lineas"])
    coste = round(sum(linea["costo_total_estimado"] for linea in orden["lineas"]), 2)

    assert orden["totales"]["unidades"] == unidades
    assert orden["totales"]["productos"] == 2
    assert orden["totales"]["costo_total_estimado"] == coste


def test_coste_unitario_por_linea_es_el_del_catalogo(client, catalogo_con_demanda):
    orden = client.get("/api/ordenes-compra").json()
    por_nombre = {linea["producto"]: linea for linea in orden["lineas"]}

    assert por_nombre["Cinta métrica 5m"]["costo_unitario"] == 2.5
    assert por_nombre["Brocha 3 pulgadas"]["costo_unitario"] == 4.0
    for linea in orden["lineas"]:
        esperado = round(linea["costo_unitario"] * linea["cantidad"], 2)
        assert linea["costo_total_estimado"] == esperado


def test_recomendaciones_incluyen_el_coste(client, catalogo_con_demanda):
    """El coste se añade a /api/recomendaciones (RF-27) sin cambiar el cálculo."""
    respuesta = client.get("/api/recomendaciones")
    assert respuesta.status_code == 200
    for recomendacion in respuesta.json()["recomendaciones"]:
        assert "costo_unitario" in recomendacion
        assert "costo_total_estimado" in recomendacion


# --- Exportación a CSV -----------------------------------------------------

def test_csv_tiene_cabecera_y_una_fila_por_producto(client, catalogo_con_demanda):
    respuesta = client.get("/api/ordenes-compra.csv")
    assert respuesta.status_code == 200
    assert "text/csv" in respuesta.headers["content-type"]
    assert "attachment" in respuesta.headers["content-disposition"]

    lineas = respuesta.text.strip().splitlines()
    # +1 cabecera, +2 productos, +1 línea en blanco, +3 líneas de totales
    assert len(lineas) == 7
    assert lineas[0].startswith("﻿")
    assert "Producto" in lineas[0]
    assert ";" in lineas[0]


def test_csv_empieza_con_bom_utf8(client, catalogo_con_demanda):
    """Sin BOM, Excel lee el archivo como ANSI y destroza las tildes."""
    respuesta = client.get("/api/ordenes-compra.csv")
    assert respuesta.content.startswith(b"\xef\xbb\xbf")


def test_csv_lleva_los_totales(client, catalogo_con_demanda):
    respuesta = client.get("/api/ordenes-compra.csv")
    texto = respuesta.text
    assert "Productos;2" in texto
    assert "Unidades;" in texto
    assert "Coste total estimado;" in texto


def test_csv_conserva_las_tildes(client, catalogo_con_demanda):
    respuesta = client.get("/api/ordenes-compra.csv")
    assert "Cinta métrica 5m" in respuesta.text
    assert "Brocha 3 pulgadas" in respuesta.text


def test_csv_sin_productos_no_falla(client, bd_temporal):
    respuesta = client.get("/api/ordenes-compra.csv")
    assert respuesta.status_code == 200
    lineas = respuesta.text.strip().splitlines()
    assert "Producto" in lineas[0]
    assert "Productos;0" in respuesta.text


# --- Exportación a HTML (imprimible) --------------------------------------

def test_html_es_documento_imprimible(client, catalogo_con_demanda):
    respuesta = client.get("/api/ordenes-compra.html")
    assert respuesta.status_code == 200
    assert "text/html" in respuesta.headers["content-type"]

    html_texto = respuesta.text
    assert html_texto.startswith("<!DOCTYPE html>")
    assert "@media print" in html_texto
    assert "@page" in html_texto
    assert "size: A4" in html_texto
    assert "window.print()" in html_texto


def test_html_tiene_la_tabla_con_las_lineas(client, catalogo_con_demanda):
    html_texto = client.get("/api/ordenes-compra.html").text

    assert "Cinta métrica 5m" in html_texto
    assert "Brocha 3 pulgadas" in html_texto
    assert "<th class='num'>Nº</th>" in html_texto
    # Cabecera + una fila por producto + fila de totales.
    assert html_texto.count("<tr>") == 4


def test_html_usa_clases_css_sin_acentos(client, catalogo_con_demanda):
    """La clase CSS de la urgencia va en ASCII: 'crítico' se traduce a 'u-critico'."""
    html_texto = client.get("/api/ordenes-compra.html").text

    assert "u-critico" in html_texto
    assert "u-crítico" not in html_texto
    assert "u-medio" in html_texto or "u-bajo" in html_texto


def test_html_muestra_los_totales(client, catalogo_con_demanda):
    orden = client.get("/api/ordenes-compra").json()
    html_texto = client.get("/api/ordenes-compra.html").text

    assert str(orden["totales"]["unidades"]) in html_texto
    assert str(orden["totales"]["costo_total_estimado"]) in html_texto


def test_html_escapa_los_nombres_con_html(client, bd_temporal):
    """Un nombre con '<script>' va escapado: la orden es una página web."""
    _insertar_producto("<script>alert(1)</script>", stock_actual=0,
                       stock_minimo=10, costo=1.0)
    _insertar_ventas("<script>alert(1)</script>", [("2026-11-15", 1)])

    html_texto = client.get("/api/ordenes-compra.html").text

    escapado = "&" + "lt;script" + "&" + "gt;alert(1)&" + "lt;/script" + "&" + "gt;"
    assert escapado in html_texto
    assert "<script>alert(1)</script>" not in html_texto


def test_html_sin_productos_avisa(client, bd_temporal):
    html_texto = client.get("/api/ordenes-compra.html").text
    assert "No hay productos que comprar" in html_texto


def test_html_deja_linea_para_el_proveedor(client, catalogo_con_demanda):
    """No hay tabla de proveedores (RF-43): la línea se rellena a mano."""
    html_texto = client.get("/api/ordenes-compra.html").text
    assert "Proveedor" in html_texto
    assert "RF-43" in html_texto


# --- Coherencia entre las tres salidas ------------------------------------

def test_json_csv_y_html_dicen_lo_mismo(client, catalogo_con_demanda):
    orden = client.get("/api/ordenes-compra").json()
    csv_texto = client.get("/api/ordenes-compra.csv").text
    html_texto = client.get("/api/ordenes-compra.html").text

    for linea in orden["lineas"]:
        assert linea["producto"] in csv_texto
        assert linea["producto"] in html_texto
