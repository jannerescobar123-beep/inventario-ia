"""
Pruebas de humo de la API (ADR-004 / registro v0.3.1).

Verifican que cada endpoint del contrato (docs/openapi.yaml) responde con la
estructura esperada sobre una base de datos temporal con datos sembrados,
sin tocar backend/datos/inventario.db.

Ejecución desde la raíz del repositorio:
    backend/.venv/bin/python -m pytest backend/tests/ -v
"""
import sys
from datetime import date, timedelta
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
def client(tmp_path, monkeypatch):
    """Cliente de prueba con una BD temporal sembrada con 2 productos."""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_inventario.db")
    database.init_db()

    conn = database.get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO productos
               (sku, nombre, categoria, costo, precio_venta,
                stock_actual, stock_minimo, nombre_norm)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("MART-001", "Martillo profesional", "Herramientas",
             25.0, 44.0, 10, 5, normalizar_texto("Martillo profesional")),
        )
        cursor.execute(
            """INSERT INTO productos
               (sku, nombre, categoria, costo, precio_venta,
                stock_actual, stock_minimo, nombre_norm)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TORN-001", "TornilloMetrico 12mm", "Fijaciones",
             0.5, 1.2, 200, 50, normalizar_texto("TornilloMetrico 12mm")),
        )
        # 10 días de ventas del martillo (3/día) para predicción y cobertura
        hoy = date.today()
        for dia in range(10):
            fecha = (hoy - timedelta(days=dia)).isoformat()
            cursor.execute(
                """INSERT INTO ventas
                   (fecha, producto, producto_norm, cantidad, precio)
                   VALUES (?, ?, ?, ?, ?)""",
                (fecha, "Martillo profesional",
                 normalizar_texto("Martillo profesional"), 3, 44.0),
            )
        conn.commit()
    finally:
        conn.close()

    # lifespan (init_db) al entrar en el contexto
    from backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "version" in r.json()


def test_kpis(client):
    r = client.get("/api/kpis")
    assert r.status_code == 200
    datos = r.json()
    assert datos["unidades_vendidas"] == 30  # 3/día × 10 días
    assert datos["ventas_totales"] == pytest.approx(30 * 44.0)
    assert datos["ticket_promedio"] >= 0


def test_productos(client):
    r = client.get("/api/productos")
    assert r.status_code == 200
    filas = r.json()
    assert len(filas) == 2
    assert {f["nombre"] for f in filas} == {
        "Martillo profesional", "TornilloMetrico 12mm"
    }


def test_rotacion_cobertura_sin_factor_30(client):
    """RF-13: dias_cobertura = stock / (ventas_ventana / 30)."""
    r = client.get("/api/rotacion")
    assert r.status_code == 200
    datos = r.json()
    martillo = next(
        p for p in datos["productos"] if p["nombre"] == "Martillo profesional"
    )
    # 30 unidades en la ventana de 30 días -> 1/día -> cobertura = stock/1
    assert martillo["total_vendido_30d"] == 30
    assert martillo["dias_cobertura"] == pytest.approx(10.0, abs=0.11)
    # Sin ventas registradas jamás -> cobertura null y razon sin_ventas
    tornillo = next(
        p for p in datos["productos"] if p["nombre"] == "TornilloMetrico 12mm"
    )
    assert tornillo["dias_cobertura"] is None
    assert any(m == "TornilloMetrico 12mm" for m in datos["muertos"])


def test_predicciones(client):
    r = client.get("/api/predicciones/1")
    assert r.status_code == 200
    datos = r.json()
    assert set(datos["predicciones"]) == {"7_dias", "14_dias", "30_dias"}
    assert datos["metodo"] == "media_movil_simple"
    assert datos["historico_dias"] == 10


def test_predicciones_producto_inexistente(client):
    r = client.get("/api/predicciones/9999")
    assert r.status_code == 404


def test_predicciones_sin_historial(client):
    """Producto sin ventas -> 400 (RF-18 requiere histórico)."""
    r = client.get("/api/predicciones/2")
    assert r.status_code == 400


def test_abc(client):
    r = client.get("/api/abc")
    assert r.status_code == 200
    datos = r.json()
    assert datos["total_productos"] == 2
    # El martillo (10×44=440) concentra >80% del valor -> clase A
    assert any(
        p["nombre"] == "Martillo profesional" for p in datos["clases"]["A"]
    )


def test_capital(client):
    r = client.get("/api/capital")
    assert r.status_code == 200
    datos = r.json()
    # 10×25 + 200×0.5 = 250 + 100 = 350
    assert datos["total_capital_inmovilizado"] == pytest.approx(350.0)
    assert "Martillo profesional" in datos["por_producto"]


def test_estacionalidad(client):
    r = client.get("/api/estacionalidad")
    assert r.status_code == 200
    assert "estacional" in r.json()
    r_producto = client.get("/api/estacionalidad?producto=Martillo profesional")
    assert r_producto.status_code == 200


def test_recomendaciones(client):
    r = client.get("/api/recomendaciones")
    assert r.status_code == 200
    datos = r.json()
    assert datos["lead_time_asumido"] == 7
    assert isinstance(datos["recomendaciones"], list)


def test_alertas(client):
    r = client.get("/api/alertas")
    assert r.status_code == 200
    datos = r.json()
    assert "riesgo_agotamiento" in datos
    assert "comportamiento" in datos
    # Martillo: stock 10, mínimo 5 -> 10 <= 7.5? No. Tornillo: 200 <= 75? No.
    # Ninguno en alerta con estos datos (umbral 1.5×mínimo)
    assert isinstance(datos["riesgo_agotamiento"], list)


def test_importar_extension_no_soportada(client):
    r = client.post(
        "/api/importar",
        files={"file": ("notas.txt", b"contenido", "text/plain")},
    )
    assert r.status_code == 400
    assert "Formato no soportado" in r.json()["detail"]


def test_importar_csv_minimo(client):
    """CSV con las 4 columnas básicas crea 1 venta y 1 producto."""
    csv = (
        "fecha,producto,cantidad,precio\n"
        f"{date.today().isoformat()},Clavo 40mm,5,0.8\n"
    ).encode("utf-8")
    r = client.post(
        "/api/importar",
        files={"file": ("ventas.csv", csv, "text/csv")},
    )
    assert r.status_code == 200
    datos = r.json()
    assert datos["total_ventas"] == 1
    assert datos["errores"] == []
    assert datos["productos_creados"] == 1


def test_chat_mensaje_vacio(client):
    r = client.post("/api/chat", json={"mensaje": ""})
    assert r.status_code == 400


def test_chat_contexto_deterministico_sin_ollama(client, monkeypatch):
    """Sin Ollama responde 200 con los datos reales en el mensaje."""
    # Fuerza la ruta de excepción apuntando a un puerto muerto
    monkeypatch.setattr("backend.api.main.OLLAMA_URL", "http://127.0.0.1:1")
    r = client.post("/api/chat", json={"mensaje": "¿Cuánto vendí?"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["modelo"] is None
    assert "datos reales" in datos["respuesta"]


def test_reparar_resumen_compra_rellena_criticos():
    """El modelo a veces omite el número de críticos en la primera línea."""
    from backend.api.main import _reparar_resumen_compra

    contexto = {
        "recomendaciones_compra": {
            "total_productos_a_comprar": 9,
            "urgencia_critica": 6,
            "productos": [],
        }
    }
    texto = "Hay 9 productos para comprar, críticos.\nMartillo: comprar 75."
    salida = _reparar_resumen_compra(texto, contexto)
    assert salida.startswith("Hay 9 productos para comprar, 6 críticos.")


def test_reparar_resumen_compra_sin_compras_no_toca_nada():
    from backend.api.main import _reparar_resumen_compra

    texto = "Hay 2 productos para comprar, 1 críticos."
    assert _reparar_resumen_compra(texto, {}) == texto


def test_openapi_sincronizado_con_rutas():
    """Las 13 rutas del contrato deben existir en la app (ADR-004)."""
    import yaml

    from backend.api.main import app

    contrato = yaml.safe_load((RAIZ / "docs" / "openapi.yaml").read_text())
    rutas_contrato = set(contrato["paths"])
    rutas_app = {r.path for r in app.routes if hasattr(r, "path")}
    faltan = rutas_contrato - rutas_app
    assert not faltan, f"Rutas en el contrato sin implementar: {faltan}"
