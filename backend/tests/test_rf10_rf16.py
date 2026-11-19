"""
Pruebas de RF-10 (tendencias por día, semana y mes) y RF-16 (comparación de
periodos).

Trabajan sobre una base de datos temporal: nunca tocan
backend/datos/inventario.db.

Ejecución desde la raíz del repositorio:
    backend/.venv/Scripts/python.exe -m pytest backend/tests/test_rf10_rf16.py -v
"""
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fastapi.testclient import TestClient  # noqa: E402

import backend.api.database as database  # noqa: E402
from backend.api.tendencias import _periodo_de  # noqa: E402


def _insertar_venta(fecha, producto="Martillo", cantidad=2, precio=10.0):
    """Insertar una fila de venta. No hace falta catálogo para tendencias."""
    conn = database.get_db()
    try:
        conn.execute(
            """INSERT INTO ventas (fecha, producto, producto_norm, cantidad, precio)
               VALUES (?, ?, ?, ?, ?)""",
            (fecha, producto, producto.upper(), cantidad, precio),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def bd_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_rf10.db")
    database.init_db()
    return database.DB_PATH


@pytest.fixture()
def client(bd_temporal):
    from backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client


# --- RF-10: semanas ISO ----------------------------------------------------

@pytest.mark.parametrize(
    "fecha, esperado",
    [
        (date(2025, 12, 28), "2025-W52"),  # domingo: última semana completa de 2025
        (date(2025, 12, 29), "2026-W01"),  # lunes cuyo jueves ya es de 2026
        (date(2026, 1, 1), "2026-W01"),
        (date(2026, 1, 4), "2026-W01"),    # domingo de esa misma semana
        (date(2026, 11, 5), "2026-W45"),
    ],
)
def test_semana_es_iso_de_verdad(fecha, esperado):
    """
    El cambio de año es donde `strftime('%W')` de SQLite se equivoca.

    La semana del 29 de diciembre de 2025 pertenece a 2026 porque su jueves es
    el 1 de enero: eso es la regla ISO, y es lo que se usa aquí.
    """
    assert _periodo_de(fecha, "semana") == esperado


# --- RF-10: serie diaria ---------------------------------------------------

def test_serie_diaria_rellena_los_dias_sin_ventas(client, bd_temporal):
    """Un día sin vender es información: aparece con 0, no como hueco."""
    _insertar_venta("2026-11-10", cantidad=3)
    _insertar_venta("2026-11-14", cantidad=5)

    respuesta = client.get(
        "/api/tendencias", params={"granularidad": "dia",
                                   "desde": "2026-11-10", "hasta": "2026-11-14"}
    )
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()

    assert datos["granularidad"] == "dia"
    assert len(datos["puntos"]) == 5
    unidades = {p["periodo"]: p["unidades"] for p in datos["puntos"]}
    assert unidades == {
        "2026-11-10": 3,
        "2026-11-11": 0,
        "2026-11-12": 0,
        "2026-11-13": 0,
        "2026-11-14": 5,
    }


def test_serie_diaria_suma_varias_ventas_del_mismo_dia(client, bd_temporal):
    _insertar_venta("2026-11-10", cantidad=3, precio=10.0)
    _insertar_venta("2026-11-10", cantidad=2, precio=10.0)

    datos = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-11-10", "hasta": "2026-11-10"},
    ).json()

    punto = datos["puntos"][0]
    assert punto["unidades"] == 5
    assert punto["ingresos"] == 50.0
    assert punto["num_ventas"] == 2


def test_serie_calcula_precio_medio_e_ingreso_por_venta(client, bd_temporal):
    """Dos nombres explícitos: no hay dos «ticket» con definiciones opuestas."""
    _insertar_venta("2026-11-10", cantidad=2, precio=15.0)   # 30 en 1 venta
    _insertar_venta("2026-11-10", cantidad=3, precio=10.0)   # 30 en 1 venta

    punto = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-11-10", "hasta": "2026-11-10"},
    ).json()["puntos"][0]

    assert punto["unidades"] == 5
    assert punto["ingresos"] == 60.0
    assert punto["precio_medio_unidad"] == 12.0    # 60 / 5 unidades
    assert punto["ingresos_por_venta"] == 30.0     # 60 / 2 filas


# --- RF-10: serie semanal y mensual ---------------------------------------

def test_serie_semanal_no_mezcla_diciembre_con_enero(client, bd_temporal):
    _insertar_venta("2025-12-28", cantidad=4)  # 2025-W52
    _insertar_venta("2025-12-29", cantidad=7)  # 2026-W01

    datos = client.get(
        "/api/tendencias",
        params={"granularidad": "semana",
                "desde": "2025-12-28", "hasta": "2026-01-04"},
    ).json()

    periodos = [p["periodo"] for p in datos["puntos"]]
    assert periodos == ["2025-W52", "2026-W01"]
    assert [p["unidades"] for p in datos["puntos"]] == [4, 7]


def test_serie_semanal_etiqueta_el_rango_de_fechas(client, bd_temporal):
    _insertar_venta("2025-12-29", cantidad=1)

    datos = client.get(
        "/api/tendencias",
        params={"granularidad": "semana",
                "desde": "2025-12-29", "hasta": "2026-01-04"},
    ).json()

    assert datos["puntos"][0]["etiqueta"] == "Sem 01 · 29 dic–4 ene"


def test_serie_mensual_agrupa_por_mes(client, bd_temporal):
    _insertar_venta("2026-09-15", cantidad=2)
    _insertar_venta("2026-09-20", cantidad=3)
    _insertar_venta("2026-10-02", cantidad=5)

    datos = client.get(
        "/api/tendencias",
        params={"granularidad": "mes", "desde": "2026-09-01", "hasta": "2026-10-31"},
    ).json()

    assert [(p["periodo"], p["unidades"]) for p in datos["puntos"]] == [
        ("2026-09", 5),
        ("2026-10", 5),
    ]
    assert datos["puntos"][1]["etiqueta"] == "oct 2026"


# --- RF-10: resumen y errores ---------------------------------------------

def test_resumen_detecta_que_las_ventas_suben(client, bd_temporal):
    for dia, cantidad in [(1, 1), (2, 2), (3, 4), (4, 8)]:
        _insertar_venta(f"2026-11-0{dia}", cantidad=cantidad)

    resumen = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-11-01", "hasta": "2026-11-04"},
    ).json()["resumen"]

    assert resumen["direccion"] == "sube"
    assert resumen["pendiente_unidades_por_periodo"] > 0
    assert resumen["unidades_totales"] == 15
    assert resumen["periodos"] == 4


def test_resumen_detecta_que_las_ventas_bajan(client, bd_temporal):
    for dia, cantidad in [(1, 8), (2, 4), (3, 2), (4, 1)]:
        _insertar_venta(f"2026-11-0{dia}", cantidad=cantidad)

    resumen = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-11-01", "hasta": "2026-11-04"},
    ).json()["resumen"]

    assert resumen["direccion"] == "baja"


def test_resumen_detecta_ventas_estables(client, bd_temporal):
    for dia in (1, 2, 3, 4):
        _insertar_venta(f"2026-11-0{dia}", cantidad=5)

    resumen = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-11-01", "hasta": "2026-11-04"},
    ).json()["resumen"]

    assert resumen["direccion"] == "estable"
    assert resumen["pendiente_relativa_pct"] == 0.0


def test_serie_sin_ventas_devuelve_periodos_a_cero(client, bd_temporal):
    datos = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-11-01", "hasta": "2026-11-03"},
    ).json()

    assert len(datos["puntos"]) == 3
    assert all(p["unidades"] == 0 for p in datos["puntos"])
    assert all(p["precio_medio_unidad"] is None for p in datos["puntos"])


def test_ventana_mensual_por_defecto_son_doce_meses_completos(client, bd_temporal):
    """
    Regresión: la ventana se mide en periodos, no en días.

    Con la versión anterior (`fin - 334 días`) el primer mes quedaba cortado y
    una venta del día 1 de ese mes desaparecía de la serie.
    """
    _insertar_venta("2025-12-01", cantidad=7)
    _insertar_venta("2026-11-10", cantidad=3)

    datos = client.get("/api/tendencias", params={"granularidad": "mes"}).json()

    assert datos["puntos"][0]["periodo"] == "2025-12"
    assert datos["puntos"][0]["unidades"] == 7
    assert len(datos["puntos"]) == 12


def test_ventana_semanal_por_defecto_son_veintiseis_semanas(client, bd_temporal):
    """Ancla en 2026-W45: 26 semanas atrás empiezan el lunes 11 de mayo."""
    _insertar_venta("2026-05-11", cantidad=4)   # W20, primer día de la ventana
    _insertar_venta("2026-11-05", cantidad=2)

    datos = client.get("/api/tendencias", params={"granularidad": "semana"}).json()

    assert datos["puntos"][0]["periodo"] == "2026-W20"
    assert datos["desde"] == "2026-05-11"
    assert len(datos["puntos"]) == 26


def test_serie_recorta_los_extremos_sin_datos(client, bd_temporal):
    """El relleno de antes de la primera venta no se devuelve: aplasta la gráfica."""
    _insertar_venta("2026-09-15", cantidad=3)
    _insertar_venta("2026-09-20", cantidad=4)

    datos = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-09-01", "hasta": "2026-09-30"},
    ).json()

    assert datos["puntos"][0]["periodo"] == "2026-09-15"
    assert datos["puntos"][-1]["periodo"] == "2026-09-20"
    assert len(datos["puntos"]) == 6
    assert datos["desde"] == "2026-09-15"
    # La ventana que se pidió queda registrada, por si hace falta explicarla.
    assert datos["ventana_solicitada"] == {"desde": "2026-09-01", "hasta": "2026-09-30"}


def test_serie_conserva_los_huecos_intermedios(client, bd_temporal):
    """Un mes sin vender entre dos con ventas es información, no relleno."""
    _insertar_venta("2026-09-01", cantidad=1)
    _insertar_venta("2026-09-30", cantidad=1)

    datos = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-09-01", "hasta": "2026-09-30"},
    ).json()

    assert len(datos["puntos"]) == 30
    assert datos["puntos"][10]["unidades"] == 0


def test_serie_se_ancla_en_la_ultima_venta_no_en_hoy(client, bd_temporal):
    """
    Si el archivo importado es antiguo, la serie termina donde terminan los
    datos, no donde termina el calendario del equipo.
    """
    _insertar_venta("2026-03-15", cantidad=1)

    datos = client.get("/api/tendencias", params={"granularidad": "dia"}).json()

    assert datos["ancla"] == "2026-03-15"
    assert datos["hasta"] == "2026-03-15"
    assert datos["puntos"][-1]["periodo"] == "2026-03-15"


def test_granularidad_invalida_devuelve_400(client, bd_temporal):
    respuesta = client.get("/api/tendencias", params={"granularidad": "trimestre"})
    assert respuesta.status_code == 400
    assert "granularidad" in respuesta.json()["detail"]


def test_rango_invertido_devuelve_400(client, bd_temporal):
    respuesta = client.get(
        "/api/tendencias",
        params={"granularidad": "dia", "desde": "2026-11-10", "hasta": "2026-11-01"},
    )
    assert respuesta.status_code == 400


# --- RF-16: comparación de periodos ---------------------------------------

def test_semana_actual_contra_la_anterior(client, bd_temporal):
    # Semana 44: 26 oct – 1 nov. Semana 45: 2 – 8 nov.
    _insertar_venta("2026-10-28", cantidad=10, precio=5.0)
    _insertar_venta("2026-11-04", cantidad=15, precio=5.0)

    datos = client.get(
        "/api/comparacion", params={"tipo": "semana", "contra": "anterior"}
    ).json()

    assert datos["disponible"] is True
    assert datos["actual"]["periodo"] == "2026-W45"
    assert datos["referencia"]["periodo"] == "2026-W44"
    assert datos["actual"]["unidades"] == 15
    assert datos["referencia"]["unidades"] == 10
    assert datos["variacion"]["unidades"] == 5
    assert datos["variacion"]["unidades_pct"] == 50.0


def test_mes_actual_contra_el_anterior(client, bd_temporal):
    _insertar_venta("2026-10-10", cantidad=20, precio=2.0)
    _insertar_venta("2026-10-20", cantidad=10, precio=2.0)
    _insertar_venta("2026-11-05", cantidad=15, precio=2.0)

    datos = client.get(
        "/api/comparacion", params={"tipo": "mes", "contra": "anterior"}
    ).json()

    assert datos["actual"]["periodo"] == "2026-11"
    assert datos["referencia"]["periodo"] == "2026-10"
    assert datos["referencia"]["unidades"] == 30
    assert datos["actual"]["unidades"] == 15
    assert datos["variacion"]["unidades"] == -15
    assert datos["variacion"]["unidades_pct"] == -50.0
    assert datos["variacion"]["ingresos_pct"] == -50.0


def test_anio_anterior_sin_datos_no_se_inventa_un_porcentaje(client, bd_temporal):
    """
    El demo solo tiene tres meses: aquí no hay año anterior. La respuesta lo
    dice en vez de devolver un -100 % que parecería una caída real.
    """
    _insertar_venta("2026-11-05", cantidad=10)

    datos = client.get(
        "/api/comparacion", params={"tipo": "mes", "contra": "anio_anterior"}
    ).json()

    assert datos["disponible"] is False
    assert datos["variacion"] is None
    assert "año anterior" in datos["motivo"]


def test_anio_anterior_con_datos_si_compara(client, bd_temporal):
    """Con dos años de histórico, la comparación anual funciona."""
    _insertar_venta("2025-11-10", cantidad=40, precio=3.0)
    _insertar_venta("2026-11-10", cantidad=50, precio=3.0)

    datos = client.get(
        "/api/comparacion", params={"tipo": "mes", "contra": "anio_anterior"}
    ).json()

    assert datos["disponible"] is True
    assert datos["actual"]["periodo"] == "2026-11"
    assert datos["referencia"]["periodo"] == "2025-11"
    assert datos["variacion"]["unidades"] == 10
    assert datos["variacion"]["unidades_pct"] == 25.0


def test_periodo_en_curso_se_marca_incompleto(client, bd_temporal):
    """
    Comparar un mes en curso contra uno cerrado exagera la caída. El dato no
    se corrige (no se inventa un método), pero se avisa.
    """
    _insertar_venta("2026-10-15", cantidad=30)
    _insertar_venta("2026-11-05", cantidad=10)

    datos = client.get(
        "/api/comparacion", params={"tipo": "mes", "contra": "anterior"}
    ).json()

    assert datos["completo"] is False
    assert datos["dias_con_datos"] == 5
    assert datos["dias_totales_periodo"] == 30
    assert "en curso" in datos["nota"]


def test_periodo_cerrado_se_marca_completo(client, bd_temporal):
    _insertar_venta("2026-10-15", cantidad=30)
    _insertar_venta("2026-11-30", cantidad=10)  # último día del mes

    datos = client.get(
        "/api/comparacion", params={"tipo": "mes", "contra": "anterior"}
    ).json()

    assert datos["completo"] is True
    assert datos["nota"] is None


def test_comparacion_anclada_en_la_ultima_venta(client, bd_temporal):
    _insertar_venta("2026-03-15", cantidad=4)

    datos = client.get(
        "/api/comparacion", params={"tipo": "mes", "contra": "anterior"}
    ).json()

    assert datos["actual"]["periodo"] == "2026-03"
    assert datos["referencia"]["periodo"] == "2026-02"
    assert datos["disponible"] is False  # febrero no tiene ventas


def test_comparacion_de_semana_con_anio_anterior_devuelve_400(client, bd_temporal):
    respuesta = client.get(
        "/api/comparacion", params={"tipo": "semana", "contra": "anio_anterior"}
    )
    assert respuesta.status_code == 400
    assert "año anterior" in respuesta.json()["detail"]


def test_tipo_de_comparacion_invalido_devuelve_400(client, bd_temporal):
    respuesta = client.get("/api/comparacion", params={"tipo": "trimestre"})
    assert respuesta.status_code == 400


def test_contra_invalido_devuelve_400(client, bd_temporal):
    respuesta = client.get("/api/comparacion", params={"contra": "siempre"})
    assert respuesta.status_code == 400
