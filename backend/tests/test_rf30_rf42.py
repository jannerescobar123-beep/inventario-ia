"""
Pruebas de RF-30 (umbrales de alerta configurables por producto o categoría) y
RF-42 (stock máximo por producto).

Igual que el resto de la suite, trabajan sobre una base de datos temporal: nunca
tocan backend/datos/inventario.db.

La prueba que protege todo lo anterior es
`test_sin_configurar_nada_las_alertas_son_las_de_siempre`: si eso pasa, el
cambio no ha alterado el comportamiento de fábrica.

Ejecución desde la raíz del repositorio:
    backend/.venv/Scripts/python.exe -m pytest backend/tests/test_rf30_rf42.py -v
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


# --- Utilidades ------------------------------------------------------------

def _insertar_producto(nombre, categoria="Herramientas", stock_actual=10,
                       stock_minimo=5, precio_venta=44.0, **extra):
    """Insertar un producto directamente, sin pasar por la API."""
    columnas = [
        "sku", "nombre", "nombre_norm", "categoria", "unidad", "costo",
        "precio_venta", "stock_actual", "stock_minimo",
    ]
    valores = [
        nombre[:8].upper().replace(" ", ""), nombre, normalizar_texto(nombre),
        categoria, "unidad", 10.0, precio_venta, stock_actual, stock_minimo,
    ]
    for columna, valor in extra.items():
        columnas.append(columna)
        valores.append(valor)

    conn = database.get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO productos ({', '.join(columnas)}) "
            f"VALUES ({', '.join('?' for _ in columnas)})",
            valores,
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _insertar_ventas(nombre, dias_y_cantidades, precio=44.0):
    """Insertar ventas de un producto: [(fecha, cantidad), ...]."""
    conn = database.get_db()
    try:
        cursor = conn.cursor()
        for fecha, cantidad in dias_y_cantidades:
            cursor.execute(
                """INSERT INTO ventas (fecha, producto, producto_norm, cantidad, precio)
                   VALUES (?, ?, ?, ?, ?)""",
                (fecha, nombre, normalizar_texto(nombre), cantidad, precio),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def bd_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_rf30_rf42.db")
    database.init_db()
    return database.DB_PATH


@pytest.fixture()
def client(bd_temporal):
    from backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client


# --- RF-30: compatibilidad (el test que protege lo que ya funcionaba) ------

def test_sin_configurar_nada_las_alertas_son_las_de_siempre(client):
    """
    Con los valores de fábrica (margen 1,5) el umbral sigue siendo el de antes.

    stock_minimo 5 -> umbral 7,5: el producto con stock 7 alerta y el de stock 8
    no. Si este test se rompe, el cambio ha alterado el comportamiento previo.
    """
    _insertar_producto("Taladro percutor", stock_actual=7, stock_minimo=5)
    _insertar_producto("Sierra circular", stock_actual=8, stock_minimo=5)

    alertas = client.get("/api/alertas").json()["riesgo_agotamiento"]
    nombres = {a["producto"] for a in alertas}

    assert "Taladro percutor" in nombres
    assert "Sierra circular" not in nombres


def test_sin_configurar_nada_las_recomendaciones_son_las_de_siempre(client):
    """
    Con el margen de fábrica (1,5) las recomendaciones son las de antes.

    Los dos productos tienen demanda de sobra, así que la cantidad a comprar
    sería mayor que 0 en ambos: lo que decide es el margen. Stock 7 <= 7,5 entra;
    stock 8 > 7,5 no.
    """
    for nombre, stock in (("Taladro percutor", 7), ("Sierra circular", 8)):
        _insertar_producto(nombre, stock_actual=stock, stock_minimo=5)
        _insertar_ventas(nombre, [("2026-11-10", 7), ("2026-11-13", 7)])

    datos = client.get("/api/recomendaciones").json()
    nombres = {r["producto"] for r in datos["recomendaciones"]}

    assert "Taladro percutor" in nombres
    assert "Sierra circular" not in nombres


def test_margen_de_categoria_tambien_aplica_a_recomendaciones(client):
    """El umbral configurado no vale solo para alertas: también filtra compras."""
    nombre = "Sierra circular"
    _insertar_producto(nombre, stock_actual=8, stock_minimo=5)
    _insertar_ventas(nombre, [("2026-11-10", 7), ("2026-11-13", 7)])

    assert client.get("/api/recomendaciones").json()["recomendaciones"] == []

    client.put("/api/umbrales/Herramientas", json={"margen_alerta": 2.0})

    nombres = {
        r["producto"]
        for r in client.get("/api/recomendaciones").json()["recomendaciones"]
    }
    assert nombres == {nombre}


def test_la_alerta_dice_que_umbral_uso(client):
    """La alerta expone el umbral aplicado: sin él, un umbral configurado es magia."""
    _insertar_producto("Taladro percutor", stock_actual=7, stock_minimo=5)

    alerta = client.get("/api/alertas").json()["riesgo_agotamiento"][0]

    assert alerta["umbral_margen"] == 1.5
    assert alerta["umbral_dias"] == 7


# --- RF-30: configuración por categoría -----------------------------------

def test_umbral_de_categoria_amplia_la_alerta(client):
    """Con margen 2,0 en la categoría, el producto con stock 8 (<= 10) ya alerta."""
    _insertar_producto("Sierra circular", stock_actual=8, stock_minimo=5)

    respuesta = client.put("/api/umbrales/Herramientas", json={"margen_alerta": 2.0})
    assert respuesta.status_code == 200, respuesta.text

    alertas = client.get("/api/alertas").json()["riesgo_agotamiento"]
    assert [a["producto"] for a in alertas] == ["Sierra circular"]
    assert alertas[0]["umbral_margen"] == 2.0


def test_umbral_de_categoria_no_distingue_mayusculas(client):
    """Configurar 'herramientas' aplica a productos con categoría 'Herramientas'."""
    _insertar_producto("Sierra circular", stock_actual=8, stock_minimo=5)

    client.put("/api/umbrales/herramientas", json={"margen_alerta": 2.0})

    alertas = client.get("/api/alertas").json()["riesgo_agotamiento"]
    assert [a["producto"] for a in alertas] == ["Sierra circular"]


def test_umbral_de_categoria_no_distingue_tildes(client):
    """
    Configurar 'ferreteria' aplica a productos con categoría 'Ferretería'.

    SQLite no quita las tildes en LOWER(), así que la comparación se hace con
    el mismo criterio que usa ADR-003 para productos y ventas.
    """
    _insertar_producto("Tornillo 8x40", categoria="Ferretería",
                       stock_actual=8, stock_minimo=5)

    respuesta = client.put("/api/umbrales/Ferreteria", json={"margen_alerta": 2.0})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["categoria"] == "Ferretería"

    alertas = client.get("/api/alertas").json()["riesgo_agotamiento"]
    assert [a["producto"] for a in alertas] == ["Tornillo 8x40"]
    assert alertas[0]["umbral_margen"] == 2.0


def test_umbral_del_producto_gana_al_de_su_categoria(client):
    """Prioridad: producto > categoría > fábrica."""
    _insertar_producto("Sierra circular", stock_actual=8, stock_minimo=5,
                       margen_alerta=1.0)

    client.put("/api/umbrales/Herramientas", json={"margen_alerta": 2.0})

    alertas = client.get("/api/alertas").json()["riesgo_agotamiento"]
    assert alertas == []  # 8 <= 5 * 1.0 no se cumple: el propio manda


def test_dias_de_inminente_configurables_por_producto(client):
    """
    Con las mismas ventas, el producto es 'inminente' o 'pronto' según su umbral.

    stock 20, ventas 7 unidades en 7 días -> 1 unidad/día -> 20 días de cobertura.
    Con el umbral de fábrica (7) es 'pronto'; configurado a 30, 'inminente'.
    """
    nombre = "Martillo profesional"
    _insertar_producto(nombre, stock_actual=20, stock_minimo=40)
    _insertar_ventas(nombre, [("2026-11-10", 3), ("2026-11-12", 4)])

    alerta = client.get("/api/alertas").json()["riesgo_agotamiento"][0]
    assert alerta["dias_estimados"] == 20
    assert alerta["riesgo"] == "agotamiento_pronto"

    cliente_id = alerta["producto_id"]
    respuesta = client.put(f"/api/productos/{cliente_id}", json={
        "nombre": nombre,
        "categoria": "Herramientas",
        "stock_actual": 20,
        "stock_minimo": 40,
        "dias_alerta_inminente": 30,
    })
    assert respuesta.status_code == 200, respuesta.text

    alerta = client.get("/api/alertas").json()["riesgo_agotamiento"][0]
    assert alerta["riesgo"] == "agotamiento_inminente"
    assert alerta["umbral_dias"] == 30


# --- RF-30: endpoints de configuración ------------------------------------

def test_get_umbrales_sin_configuracion(client):
    """Sin nada configurado devuelve los valores de fábrica y ninguna categoría."""
    datos = client.get("/api/umbrales").json()

    assert datos["por_defecto"] == {"dias_inminente": 7, "margen": 1.5}
    assert datos["categorias"] == []


def test_get_umbrales_lista_lo_configurado(client):
    _insertar_producto("Sierra circular", categoria="Herramientas")

    client.put("/api/umbrales/Herramientas", json={
        "margen_alerta": 2.0,
        "dias_alerta_inminente": 10,
    })

    datos = client.get("/api/umbrales").json()
    assert datos["categorias"] == [{
        "categoria": "Herramientas",
        "dias_inminente": 10,
        "margen": 2.0,
        "propio_dias_inminente": 10,
        "propio_margen": 2.0,
    }]


def test_put_umbral_de_categoria_inexistente_da_404(client):
    """Una errata no debe crear configuración fantasma."""
    respuesta = client.put("/api/umbrales/Herramienta", json={"margen_alerta": 2.0})

    assert respuesta.status_code == 404
    assert client.get("/api/umbrales").json()["categorias"] == []


def test_put_umbral_con_null_vuelve_al_valor_de_fabrica(client):
    _insertar_producto("Sierra circular", categoria="Herramientas")
    client.put("/api/umbrales/Herramientas", json={"margen_alerta": 2.0})

    respuesta = client.put("/api/umbrales/Herramientas", json={
        "margen_alerta": None,
        "dias_alerta_inminente": None,
    })

    assert respuesta.status_code == 200
    assert respuesta.json()["margen"] == 1.5
    assert respuesta.json()["configurada"] is False
    assert client.get("/api/umbrales").json()["categorias"] == []


@pytest.mark.parametrize("cuerpo", [
    {"margen_alerta": 0},
    {"margen_alerta": -1},
    {"dias_alerta_inminente": 0},
])
def test_put_umbral_invalido_da_422(client, cuerpo):
    _insertar_producto("Sierra circular", categoria="Herramientas")

    assert client.put("/api/umbrales/Herramientas", json=cuerpo).status_code == 422


# --- RF-42: stock máximo ---------------------------------------------------

def test_alta_guarda_stock_maximo(client):
    respuesta = client.post("/api/productos", json={
        "nombre": "Cinta métrica 5m",
        "categoria": "Herramientas",
        "stock_actual": 10,
        "stock_minimo": 4,
        "stock_maximo": 40,
    })

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["stock_maximo"] == 40


def test_editar_sin_enviar_umbrales_no_los_borra(client):
    """
    Un PUT que no menciona los umbrales conserva los que había.

    El formulario actual no envía esos campos: borrarlos en cada edición sería
    perder configuración sin que nadie lo haya pedido.
    """
    creado = client.post("/api/productos", json={
        "nombre": "Cinta métrica 5m",
        "categoria": "Herramientas",
        "stock_actual": 10,
        "stock_minimo": 4,
        "stock_maximo": 40,
        "margen_alerta": 2.0,
        "dias_alerta_inminente": 15,
    }).json()

    respuesta = client.put(f"/api/productos/{creado['id']}", json={
        "nombre": "Cinta métrica 5m",
        "categoria": "Herramientas",
        "stock_actual": 12,
        "stock_minimo": 4,
    })

    assert respuesta.status_code == 200, respuesta.text
    producto = respuesta.json()
    assert producto["stock_actual"] == 12
    assert producto["stock_maximo"] == 40
    assert producto["margen_alerta"] == 2.0
    assert producto["dias_alerta_inminente"] == 15


def test_editar_con_null_explicito_borra_el_umbral(client):
    creado = client.post("/api/productos", json={
        "nombre": "Cinta métrica 5m",
        "categoria": "Herramientas",
        "stock_actual": 10,
        "stock_minimo": 4,
        "stock_maximo": 40,
    }).json()

    respuesta = client.put(f"/api/productos/{creado['id']}", json={
        "nombre": "Cinta métrica 5m",
        "stock_actual": 10,
        "stock_minimo": 4,
        "stock_maximo": None,
    })

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["stock_maximo"] is None


def test_alerta_de_exceso_de_stock(client):
    """Un producto por encima de su máximo aparece con el capital inmovilizado."""
    _insertar_producto("Cinta métrica 5m", stock_actual=100, stock_minimo=4,
                       stock_maximo=40, precio_venta=12.5)

    exceso = client.get("/api/alertas").json()["exceso_stock"]

    assert len(exceso) == 1
    assert exceso[0]["producto"] == "Cinta métrica 5m"
    assert exceso[0]["exceso_unidades"] == 60
    assert exceso[0]["capital_inmovilizado"] == 750.0


def test_producto_sin_maximo_nunca_tiene_exceso(client):
    _insertar_producto("Cinta métrica 5m", stock_actual=500, stock_minimo=4)

    assert client.get("/api/alertas").json()["exceso_stock"] == []


def test_recomendacion_no_supera_el_maximo_del_producto(client):
    """
    Objetivo de reposición: stock_minimo (10) + demanda. Con máximo 12 y stock 4,
    la cantidad sugerida no puede pasar de 8 unidades.
    """
    nombre = "Cinta métrica 5m"
    _insertar_producto(nombre, stock_actual=4, stock_minimo=10, stock_maximo=12)
    _insertar_ventas(nombre, [("2026-11-14", 2), ("2026-11-15", 2)])

    recomendaciones = client.get("/api/recomendaciones").json()["recomendaciones"]
    sugerida = [r for r in recomendaciones if r["producto"] == nombre][0]

    assert sugerida["cantidad_sugerida"] <= 8


# --- Migración sobre una base ya existente --------------------------------

def test_migracion_anade_las_columnas_a_una_bd_antigua(tmp_path, monkeypatch):
    """init_db() debe actualizar una base creada antes de RF-30/RF-42."""
    import sqlite3

    ruta = tmp_path / "antigua.db"
    conn = sqlite3.connect(ruta)
    conn.execute("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE,
            nombre TEXT NOT NULL,
            categoria TEXT,
            costo REAL DEFAULT 0,
            precio_venta REAL DEFAULT 0,
            stock_actual INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 0,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT INTO productos (nombre, categoria, stock_actual, stock_minimo) "
        "VALUES ('Martillo viejo', 'Herramientas', 3, 5)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DB_PATH", ruta)
    database.init_db()

    conn = database.get_db()
    try:
        columnas = [c[1] for c in conn.execute("PRAGMA table_info(productos)")]
        fila = conn.execute(
            "SELECT stock_maximo, dias_alerta_inminente, margen_alerta FROM productos"
        ).fetchone()
        tablas = [
            f[0] for f in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
    finally:
        conn.close()

    assert {"stock_maximo", "dias_alerta_inminente", "margen_alerta"} <= set(columnas)
    assert tuple(fila) == (None, None, None)  # los datos existentes no se tocan
    assert "umbrales_categoria" in tablas
