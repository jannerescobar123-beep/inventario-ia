"""
Pruebas de RF-43: proveedores con su tiempo de entrega (lead time) usados en
las recomendaciones y en la orden de compra.

Trabajan sobre una base de datos temporal: nunca tocan
backend/datos/inventario.db.

Ejecución desde la raíz del repositorio:
    backend/.venv/Scripts/python.exe -m pytest backend/tests/test_rf43.py -v
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
    """Producto que entra en recomendaciones (stock por debajo del mínimo)."""
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


def _crear_proveedor(client, nombre, lead_time_dias=7, **extra):
    respuesta = client.post(
        "/api/proveedores",
        json={"nombre": nombre, "lead_time_dias": lead_time_dias, **extra},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


@pytest.fixture()
def bd_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_rf43.db")
    database.init_db()
    return database.DB_PATH


@pytest.fixture()
def client(bd_temporal):
    from backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def catalogo_con_demanda(bd_temporal):
    """Dos productos que necesitan compra y tienen demanda reciente."""
    _insertar_producto("Cinta métrica 5m", stock_actual=4, stock_minimo=10, costo=2.5)
    _insertar_producto("Brocha 3 pulgadas", categoria="Pintura", stock_actual=1,
                       stock_minimo=8, costo=4.0)
    _insertar_ventas("Cinta métrica 5m", [("2026-11-14", 2), ("2026-11-15", 2)])
    _insertar_ventas("Brocha 3 pulgadas", [("2026-11-14", 3), ("2026-11-15", 1)])
    return bd_temporal


# --- CRUD de proveedores ---------------------------------------------------

def test_alta_de_proveedor_devuelve_201_y_su_lead_time(client, bd_temporal):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=12,
                                 contacto="Ana", telefono="600 111 222")

    assert proveedor["id"] > 0
    assert proveedor["nombre"] == "Ferretería Paz"
    assert proveedor["lead_time_dias"] == 12
    assert proveedor["contacto"] == "Ana"
    assert proveedor["telefono"] == "600 111 222"
    assert proveedor["activo"] is True
    assert proveedor["productos_asignados"] == 0


def test_nombre_duplicado_sin_tildes_ni_mayusculas_devuelve_409(client, bd_temporal):
    """'Ferretería Paz' y 'FERRETERIA PAZ' son el mismo proveedor."""
    _crear_proveedor(client, "Ferretería Paz")

    respuesta = client.post(
        "/api/proveedores", json={"nombre": "FERRETERIA PAZ", "lead_time_dias": 9}
    )

    assert respuesta.status_code == 409, respuesta.text


def test_lead_time_fuera_de_rango_devuelve_422(client, bd_temporal):
    for lead_time in (0, 366, -3):
        respuesta = client.post(
            "/api/proveedores",
            json={"nombre": f"Proveedor {lead_time}", "lead_time_dias": lead_time},
        )
        assert respuesta.status_code == 422, (lead_time, respuesta.text)


def test_listado_y_solo_activos(client, bd_temporal):
    activo = _crear_proveedor(client, "Distribuciones Norte", lead_time_dias=10)
    baja = _crear_proveedor(client, "Suministros Sur", lead_time_dias=5)
    client.delete(f"/api/proveedores/{baja['id']}")

    todos = client.get("/api/proveedores").json()
    solo_activos = client.get("/api/proveedores?solo_activos=true").json()

    assert {p["id"] for p in todos} == {activo["id"], baja["id"]}
    assert [p["id"] for p in solo_activos] == [activo["id"]]
    assert todos[0]["nombre"] <= todos[1]["nombre"]


def test_editar_proveedor_cambia_lead_time(client, bd_temporal):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=12)

    respuesta = client.put(
        f"/api/proveedores/{proveedor['id']}",
        json={"nombre": "Ferretería Paz", "lead_time_dias": 3},
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["lead_time_dias"] == 3


def test_editar_con_nombre_de_otro_devuelve_409(client, bd_temporal):
    primero = _crear_proveedor(client, "Proveedor A")
    _crear_proveedor(client, "Proveedor B")

    respuesta = client.put(
        f"/api/proveedores/{primero['id']}",
        json={"nombre": "proveedor b", "lead_time_dias": 7},
    )

    assert respuesta.status_code == 409, respuesta.text


def test_baja_logica_conserva_fila_y_productos(client, catalogo_con_demanda):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=12)
    producto_id = client.get("/api/productos").json()[0]["id"]
    client.put(f"/api/productos/{producto_id}/proveedor",
               json={"proveedor_id": proveedor["id"]})

    respuesta = client.delete(f"/api/proveedores/{proveedor['id']}")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["activo"] is False
    assert respuesta.json()["productos_asignados"] == 1

    # La fila sigue en el listado completo y el producto conserva la asignación.
    todos = client.get("/api/proveedores").json()
    assert proveedor["id"] in {p["id"] for p in todos}
    producto = next(p for p in client.get("/api/productos").json() if p["id"] == producto_id)
    assert producto["proveedor_id"] == proveedor["id"]


def test_reactivar_proveedor_con_put(client, bd_temporal):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=12)
    client.delete(f"/api/proveedores/{proveedor['id']}")

    respuesta = client.put(
        f"/api/proveedores/{proveedor['id']}",
        json={"nombre": "Ferretería Paz", "lead_time_dias": 12, "activo": True},
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["activo"] is True


def test_proveedor_inexistente_devuelve_404(client, bd_temporal):
    assert client.put(
        "/api/proveedores/999", json={"nombre": "Fantasma", "lead_time_dias": 7}
    ).status_code == 404
    assert client.delete("/api/proveedores/999").status_code == 404


# --- Asignación a productos ------------------------------------------------

def test_asignar_proveedor_a_producto(client, catalogo_con_demanda):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=12)
    producto_id = client.get("/api/productos").json()[0]["id"]

    respuesta = client.put(f"/api/productos/{producto_id}/proveedor",
                           json={"proveedor_id": proveedor["id"]})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["proveedor_id"] == proveedor["id"]

    producto = next(p for p in client.get("/api/productos").json() if p["id"] == producto_id)
    assert producto["proveedor"] == "Ferretería Paz"
    assert producto["lead_time_proveedor"] == 12


def test_quitar_proveedor_con_null(client, catalogo_con_demanda):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=12)
    producto_id = client.get("/api/productos").json()[0]["id"]
    client.put(f"/api/productos/{producto_id}/proveedor",
               json={"proveedor_id": proveedor["id"]})

    respuesta = client.put(f"/api/productos/{producto_id}/proveedor",
                           json={"proveedor_id": None})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["proveedor_id"] is None
    producto = next(p for p in client.get("/api/productos").json() if p["id"] == producto_id)
    assert producto["proveedor"] is None
    assert producto["lead_time_proveedor"] is None


def test_no_se_puede_asignar_un_proveedor_de_baja(client, catalogo_con_demanda):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=12)
    client.delete(f"/api/proveedores/{proveedor['id']}")
    producto_id = client.get("/api/productos").json()[0]["id"]

    respuesta = client.put(f"/api/productos/{producto_id}/proveedor",
                           json={"proveedor_id": proveedor["id"]})

    assert respuesta.status_code == 409, respuesta.text


def test_asignacion_a_producto_inexistente_devuelve_404(client, bd_temporal):
    proveedor = _crear_proveedor(client, "Ferretería Paz")

    respuesta = client.put("/api/productos/999/proveedor",
                           json={"proveedor_id": proveedor["id"]})

    assert respuesta.status_code == 404, respuesta.text


def test_alta_de_producto_con_proveedor_inactivo_devuelve_409(client, bd_temporal):
    proveedor = _crear_proveedor(client, "Ferretería Paz")
    client.delete(f"/api/proveedores/{proveedor['id']}")

    respuesta = client.post("/api/productos", json={
        "nombre": "Taladro",
        "proveedor_id": proveedor["id"],
    })

    assert respuesta.status_code == 409, respuesta.text


# --- Lead time real en las recomendaciones ---------------------------------

def test_producto_con_proveedor_usa_su_lead_time(client, catalogo_con_demanda):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=20)
    producto = next(p for p in client.get("/api/productos").json()
                    if p["nombre"] == "Cinta métrica 5m")
    client.put(f"/api/productos/{producto['id']}/proveedor",
               json={"proveedor_id": proveedor["id"]})

    recomendaciones = client.get("/api/recomendaciones").json()["recomendaciones"]
    linea = next(r for r in recomendaciones if r["producto"] == "Cinta métrica 5m")

    assert linea["proveedor"] == "Ferretería Paz"
    assert linea["proveedor_id"] == proveedor["id"]
    assert linea["lead_time_dias"] == 20


def test_producto_sin_proveedor_conserva_los_7_dias(client, catalogo_con_demanda):
    recomendaciones = client.get("/api/recomendaciones").json()["recomendaciones"]

    assert recomendaciones
    for linea in recomendaciones:
        assert linea["proveedor"] is None
        assert linea["proveedor_id"] is None
        assert linea["lead_time_dias"] == 7


def test_lead_time_global_solo_afecta_a_los_productos_sin_proveedor(client, catalogo_con_demanda):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=20)
    producto = next(p for p in client.get("/api/productos").json()
                    if p["nombre"] == "Cinta métrica 5m")
    client.put(f"/api/productos/{producto['id']}/proveedor",
               json={"proveedor_id": proveedor["id"]})

    datos = client.get("/api/recomendaciones?lead_time=3").json()
    por_nombre = {r["producto"]: r for r in datos["recomendaciones"]}

    assert por_nombre["Cinta métrica 5m"]["lead_time_dias"] == 20
    assert por_nombre["Brocha 3 pulgadas"]["lead_time_dias"] == 3
    assert datos["lead_time_asumido"] == 3


def test_proveedor_de_baja_hace_volver_al_lead_time_global(client, catalogo_con_demanda):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=20)
    producto = next(p for p in client.get("/api/productos").json()
                    if p["nombre"] == "Cinta métrica 5m")
    client.put(f"/api/productos/{producto['id']}/proveedor",
               json={"proveedor_id": proveedor["id"]})

    client.delete(f"/api/proveedores/{proveedor['id']}")

    recomendaciones = client.get("/api/recomendaciones").json()["recomendaciones"]
    linea = next(r for r in recomendaciones if r["producto"] == "Cinta métrica 5m")

    assert linea["lead_time_dias"] == 7
    assert linea["proveedor"] is None


def test_sin_proveedores_las_recomendaciones_no_cambian(client, catalogo_con_demanda):
    """
    Regresión: sin proveedores asignados, el resultado es el de antes de RF-43.

    Se compara el cálculo con el mismo catálogo usando el lead time por defecto.
    """
    datos = client.get("/api/recomendaciones").json()
    por_nombre = {r["producto"]: r for r in datos["recomendaciones"]}

    # Valores calculados con el algoritmo anterior (lead time 7 para todos):
    # demanda de 7 días = 4 unidades => demanda_diaria = 4/7.
    for nombre in ("Cinta métrica 5m", "Brocha 3 pulgadas"):
        assert por_nombre[nombre]["lead_time_dias"] == 7
        assert por_nombre[nombre]["demanda_proyectada"] == int((4 / 7) * 7)
        assert por_nombre[nombre]["costo_unitario"] > 0


# --- Orden de compra agrupada ---------------------------------------------

def test_orden_agrupa_por_proveedor_y_suma_subtotales(client, catalogo_con_demanda):
    norte = _crear_proveedor(client, "Distribuciones Norte", lead_time_dias=10)
    sur = _crear_proveedor(client, "Suministros Sur", lead_time_dias=4)
    productos = {p["nombre"]: p for p in client.get("/api/productos").json()}
    client.put(f"/api/productos/{productos['Cinta métrica 5m']['id']}/proveedor",
               json={"proveedor_id": norte["id"]})
    client.put(f"/api/productos/{productos['Brocha 3 pulgadas']['id']}/proveedor",
               json={"proveedor_id": sur["id"]})

    orden = client.get("/api/ordenes-compra").json()

    assert len(orden["grupos"]) == 2
    grupos = {g["proveedor"]: g for g in orden["grupos"]}
    assert set(grupos) == {"Distribuciones Norte", "Suministros Sur"}
    assert grupos["Distribuciones Norte"]["lead_time_dias"] == 10
    assert grupos["Suministros Sur"]["lead_time_dias"] == 4

    # Los subtotales suman exactamente el total de la orden.
    assert sum(g["totales"]["unidades"] for g in orden["grupos"]) == orden["totales"]["unidades"]
    assert sum(g["totales"]["productos"] for g in orden["grupos"]) == orden["totales"]["productos"]


def test_orden_sin_proveedores_usa_un_grupo_propio(client, catalogo_con_demanda):
    orden = client.get("/api/ordenes-compra").json()

    assert len(orden["grupos"]) == 1
    assert orden["grupos"][0]["proveedor"] is None
    assert orden["grupos"][0]["proveedor_id"] is None
    assert orden["grupos"][0]["totales"]["productos"] == 2


def test_csv_y_html_llevan_el_proveedor(client, catalogo_con_demanda):
    proveedor = _crear_proveedor(client, "Ferretería Paz", lead_time_dias=12)
    producto = next(p for p in client.get("/api/productos").json()
                    if p["nombre"] == "Cinta métrica 5m")
    client.put(f"/api/productos/{producto['id']}/proveedor",
               json={"proveedor_id": proveedor["id"]})

    csv_texto = client.get("/api/ordenes-compra.csv").text
    html_texto = client.get("/api/ordenes-compra.html").text

    assert "Proveedor" in csv_texto.splitlines()[0]
    assert "Ferretería Paz" in csv_texto
    assert "Ferretería Paz" in html_texto
    assert "lead time 12 días" in html_texto
