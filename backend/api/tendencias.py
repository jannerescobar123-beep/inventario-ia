"""
Tendencias de venta por periodo (RF-10) y comparación de periodos (RF-16).

Este módulo solo agrega lo que ya está en la tabla `ventas`: no crea datos, no
modifica el esquema y no cambia ningún cálculo existente.

Dos ideas sostienen todo lo de aquí:

1. **Ancla temporal.** Los periodos se cuentan desde la *última venta
   registrada*, no desde el reloj del equipo. Si el archivo importado es de
   octubre, la «semana actual» es la de octubre. Es el mismo criterio que usan
   rotación (RF-11) y recomendaciones (RF-22): el histórico sigue sirviendo
   aunque el archivo no sea de hoy.

2. **Semana ISO de verdad.** Las semanas se calculan con
   `date.isocalendar()` (lunes a domingo, regla del jueves). El `strftime('%W')`
   de SQLite no es ISO: inventa una «semana 00» y descoloca el año en los
   bordes de enero.

Nombres de los campos de dinero (para no repetir el error de RF-09):
  - `precio_medio_unidad`  = ingresos / unidades vendidas
  - `ingresos_por_venta`   = ingresos / número de filas de venta
No se usa el nombre «ticket promedio» a secas porque en `/api/kpis` (RF-09)
ese nombre significa ingresos / unidades, y dos definiciones distintas con el
mismo nombre son una trampa para quien consuma la API.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

GRANULARIDADES = ("dia", "semana", "mes")
TIPOS_COMPARACION = ("semana", "mes")
CONTRA_VALIDOS = ("anterior", "anio_anterior")

# Ventana por defecto de la serie, medida en PERIODOS (no en días): 12 meses
# son 12 meses, no «hoy menos 334 días».
VENTANA_POR_DEFECTO = {"dia": 90, "semana": 26, "mes": 12}

MESES_CORTOS = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)


# --- Utilidades de periodo -------------------------------------------------

def _anchor(conn) -> date:
    """Última fecha de venta (o hoy si la tabla está vacía)."""
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha) FROM ventas")
    fila = cursor.fetchone()
    valor = fila[0] if fila else None
    if not valor:
        return datetime.now().date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _periodo_de(fecha: date, granularidad: str) -> str:
    """Clave ordenable del periodo al que pertenece una fecha."""
    if granularidad == "dia":
        return fecha.isoformat()
    if granularidad == "mes":
        return f"{fecha.year:04d}-{fecha.month:02d}"
    anio, semana, _ = fecha.isocalendar()
    return f"{anio:04d}-W{semana:02d}"


def _inicio_de(periodo: str, granularidad: str) -> date:
    """Primer día del periodo."""
    if granularidad == "dia":
        return date.fromisoformat(periodo)
    if granularidad == "mes":
        anio, mes = periodo.split("-")
        return date(int(anio), int(mes), 1)
    anio, semana = periodo.split("-W")
    return date.fromisocalendar(int(anio), int(semana), 1)


def _fin_de(periodo: str, granularidad: str) -> date:
    """Último día del periodo."""
    if granularidad == "dia":
        return date.fromisoformat(periodo)
    inicio = _inicio_de(periodo, granularidad)
    if granularidad == "mes":
        siguiente = _avanzar(periodo, granularidad, 1)
        return _inicio_de(siguiente, granularidad) - timedelta(days=1)
    return inicio + timedelta(days=6)


def _avanzar(periodo: str, granularidad: str, pasos: int = 1) -> str:
    """Periodo desplazado `pasos` posiciones (negativo = hacia atrás)."""
    inicio = _inicio_de(periodo, granularidad)
    if granularidad == "dia":
        return (inicio + timedelta(days=pasos)).isoformat()
    if granularidad == "semana":
        return _periodo_de(inicio + timedelta(weeks=pasos), "semana")
    total = (inicio.year * 12 + inicio.month - 1) + pasos
    anio, mes = divmod(total, 12)
    return f"{anio:04d}-{mes + 1:02d}"


def _etiqueta(periodo: str, granularidad: str) -> str:
    """Etiqueta legible en español para la gráfica y la tabla."""
    if granularidad == "dia":
        dia = _inicio_de(periodo, granularidad)
        return f"{dia.day} {MESES_CORTOS[dia.month - 1]}"
    if granularidad == "mes":
        anio, mes = periodo.split("-")
        return f"{MESES_CORTOS[int(mes) - 1]} {anio}"
    inicio = _inicio_de(periodo, granularidad)
    fin = _fin_de(periodo, granularidad)
    numero = periodo.split("-W")[1]
    return (
        f"Sem {numero} · {inicio.day} {MESES_CORTOS[inicio.month - 1]}"
        f"–{fin.day} {MESES_CORTOS[fin.month - 1]}"
    )


def _lista_periodos(desde: str, hasta: str, granularidad: str) -> List[str]:
    """Todos los periodos entre dos extremos, incluidos los vacíos."""
    periodo = desde
    periodos: List[str] = []
    # Tope de seguridad: una serie de más de 5000 puntos no es una gráfica,
    # es un volcado; y evita un bucle infinito si algo se desalinea.
    while periodo <= hasta and len(periodos) < 5000:
        periodos.append(periodo)
        periodo = _avanzar(periodo, granularidad, 1)
    return periodos


def _recortar_extremos(puntos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Quitar los periodos sin ventas de los extremos de la serie.

    Los huecos INTERMEDIOS se conservan: un mes sin vender entre dos con
    ventas es información real. Lo que se quita es el relleno de antes de la
    primera venta y de después de la última, que solo aplasta la gráfica.

    Si la serie entera está vacía se devuelve tal cual, para que quien la lea
    sepa cuántos periodos se consultaron.
    """
    con_datos = [indice for indice, p in enumerate(puntos) if p["num_ventas"] > 0]
    if not con_datos:
        return puntos
    return puntos[con_datos[0]: con_datos[-1] + 1]


def _pendiente(valores: List[float]) -> float:
    """Pendiente de la recta de mínimos cuadrados (unidades por periodo)."""
    n = len(valores)
    if n < 2:
        return 0.0
    media_x = (n - 1) / 2
    media_y = sum(valores) / n
    numerador = sum((i - media_x) * (v - media_y) for i, v in enumerate(valores))
    denominador = sum((i - media_x) ** 2 for i in range(n))
    if not denominador:
        return 0.0
    return numerador / denominador


def _variacion(actual: float, anterior: float) -> Optional[float]:
    """Variación porcentual. None si no hay base con la que comparar."""
    if anterior is None or anterior == 0:
        return None
    return round(((actual - anterior) / anterior) * 100, 2)


# --- RF-10: serie de ventas ------------------------------------------------

def _agregado_periodo(conn, desde: date, hasta: date) -> Dict[str, Dict[str, float]]:
    """Unidades, ingresos y número de ventas por periodo dentro del rango."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT fecha,
               COALESCE(SUM(cantidad), 0),
               COALESCE(SUM(cantidad * precio), 0),
               COUNT(*)
        FROM ventas
        WHERE fecha >= ? AND fecha <= ?
        GROUP BY fecha
        ORDER BY fecha
        """,
        (desde.isoformat(), hasta.isoformat()),
    )
    return {
        str(fecha)[:10]: {
            "unidades": float(unidades or 0),
            "ingresos": float(ingresos or 0),
            "num_ventas": int(num_ventas or 0),
        }
        for fecha, unidades, ingresos, num_ventas in cursor.fetchall()
    }


def serie_ventas(
    conn,
    granularidad: str = "mes",
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Serie de ventas agregada por día, semana o mes (RF-10).

    Los periodos sin ventas aparecen con cero: un día que no se vendió es
    información, no un hueco en la gráfica.
    """
    if granularidad not in GRANULARIDADES:
        raise ValueError(
            f"granularidad debe ser una de {GRANULARIDADES}, no {granularidad!r}"
        )

    anchor = _anchor(conn)
    fin = date.fromisoformat(hasta) if hasta else anchor
    if desde:
        inicio = date.fromisoformat(desde)
    else:
        # La ventana se cuenta en periodos completos: 12 meses hacia atrás son
        # 12 periodos, no 334 días (que dejaría el primer mes a medias).
        periodo_fin = _periodo_de(fin, granularidad)
        periodo_inicio = _avanzar(
            periodo_fin, granularidad, -(VENTANA_POR_DEFECTO[granularidad] - 1)
        )
        inicio = _inicio_de(periodo_inicio, granularidad)
    if inicio > fin:
        raise ValueError("La fecha 'desde' no puede ser posterior a 'hasta'")

    por_dia = _agregado_periodo(conn, inicio, fin)

    # Se agrega por periodo en Python para poder usar semanas ISO.
    acumulado: Dict[str, Dict[str, float]] = {}
    for fecha_texto, valores in por_dia.items():
        periodo = _periodo_de(date.fromisoformat(fecha_texto), granularidad)
        bucket = acumulado.setdefault(
            periodo, {"unidades": 0.0, "ingresos": 0.0, "num_ventas": 0}
        )
        bucket["unidades"] += valores["unidades"]
        bucket["ingresos"] += valores["ingresos"]
        bucket["num_ventas"] += valores["num_ventas"]

    primera = _periodo_de(inicio, granularidad)
    ultima = _periodo_de(fin, granularidad)
    periodos = _lista_periodos(primera, ultima, granularidad)

    puntos: List[Dict[str, Any]] = []
    anterior_unidades: Optional[float] = None
    for periodo in periodos:
        datos = acumulado.get(periodo, {"unidades": 0.0, "ingresos": 0.0, "num_ventas": 0})
        unidades = int(datos["unidades"])
        ingresos = round(datos["ingresos"], 2)
        num_ventas = int(datos["num_ventas"])
        puntos.append({
            "periodo": periodo,
            "etiqueta": _etiqueta(periodo, granularidad),
            "unidades": unidades,
            "ingresos": ingresos,
            "num_ventas": num_ventas,
            # Nombres explícitos: no hay dos «ticket» con definiciones opuestas.
            "precio_medio_unidad": round(ingresos / unidades, 2) if unidades else None,
            "ingresos_por_venta": round(ingresos / num_ventas, 2) if num_ventas else None,
            "variacion_unidades_pct": _variacion(unidades, anterior_unidades),
        })
        anterior_unidades = unidades

    puntos = _recortar_extremos(puntos)

    valores = [p["unidades"] for p in puntos]
    pendiente = _pendiente(valores)
    media = (sum(valores) / len(valores)) if valores else 0
    pendiente_relativa = (pendiente / media * 100) if media else 0
    if pendiente_relativa > 5:
        direccion = "sube"
    elif pendiente_relativa < -5:
        direccion = "baja"
    else:
        direccion = "estable"

    return {
        "granularidad": granularidad,
        "desde": (
            _inicio_de(puntos[0]["periodo"], granularidad).isoformat()
            if puntos else inicio.isoformat()
        ),
        "hasta": fin.isoformat(),
        "ancla": anchor.isoformat(),
        "ventana_solicitada": {
            "desde": inicio.isoformat(),
            "hasta": fin.isoformat(),
        },
        "puntos": puntos,
        "resumen": {
            "periodos": len(puntos),
            "unidades_totales": int(sum(valores)),
            "ingresos_totales": round(sum(p["ingresos"] for p in puntos), 2),
            "media_unidades_por_periodo": round(media, 2),
            "pendiente_unidades_por_periodo": round(pendiente, 3),
            "pendiente_relativa_pct": round(pendiente_relativa, 2),
            "direccion": direccion,
        },
    }


# --- RF-16: comparación de periodos ---------------------------------------

def _totales_periodo(conn, periodo: str, granularidad: str) -> Dict[str, Any]:
    """Totales de un periodo concreto."""
    inicio = _inicio_de(periodo, granularidad)
    fin = _fin_de(periodo, granularidad)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COALESCE(SUM(cantidad), 0),
               COALESCE(SUM(cantidad * precio), 0),
               COUNT(*)
        FROM ventas
        WHERE fecha >= ? AND fecha <= ?
        """,
        (inicio.isoformat(), fin.isoformat()),
    )
    unidades, ingresos, num_ventas = cursor.fetchone()
    unidades = int(unidades or 0)
    ingresos = float(ingresos or 0)
    num_ventas = int(num_ventas or 0)
    return {
        "periodo": periodo,
        "etiqueta": _etiqueta(periodo, granularidad),
        "desde": inicio.isoformat(),
        "hasta": fin.isoformat(),
        "unidades": unidades,
        "ingresos": round(ingresos, 2),
        "num_ventas": num_ventas,
        "precio_medio_unidad": round(ingresos / unidades, 2) if unidades else None,
        "ingresos_por_venta": round(ingresos / num_ventas, 2) if num_ventas else None,
        "tiene_datos": num_ventas > 0,
    }


def comparar_periodos(
    conn,
    tipo: str = "semana",
    contra: str = "anterior",
    periodo: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Comparar un periodo con otro (RF-16).

    - `tipo`: `semana` o `mes`.
    - `contra`: `anterior` (periodo inmediatamente anterior) o
      `anio_anterior` (el mismo periodo del año pasado, solo para `mes`).
    - `periodo`: periodo concreto a comparar; por defecto el de la última venta.

    Si el periodo de referencia no tiene ventas, devuelve
    `disponible: false` con el motivo: nunca un 0 % que parece una caída real.
    """
    if tipo not in TIPOS_COMPARACION:
        raise ValueError(f"tipo debe ser uno de {TIPOS_COMPARACION}, no {tipo!r}")
    if contra not in CONTRA_VALIDOS:
        raise ValueError(f"contra debe ser uno de {CONTRA_VALIDOS}, no {contra!r}")
    if contra == "anio_anterior" and tipo != "mes":
        raise ValueError("La comparación con el año anterior solo aplica a 'mes'")

    anchor = _anchor(conn)
    actual = periodo or _periodo_de(anchor, tipo)

    if contra == "anterior":
        referencia = _avanzar(actual, tipo, -1)
    else:
        referencia = _avanzar(actual, tipo, -12)

    datos_actual = _totales_periodo(conn, actual, tipo)
    datos_referencia = _totales_periodo(conn, referencia, tipo)

    if not datos_referencia["tiene_datos"]:
        motivo = (
            "No hay ventas registradas en el mismo mes del año anterior."
            if contra == "anio_anterior"
            else "No hay ventas registradas en el periodo anterior."
        )
        return {
            "disponible": False,
            "motivo": motivo,
            "tipo": tipo,
            "contra": contra,
            "actual": datos_actual,
            "referencia": datos_referencia,
            "variacion": None,
        }

    # Un mes (o una semana) en curso está incompleto: compararlo con uno
    # cerrado exagera la caída. Se marca para que quien lea sepa qué compara.
    fin_actual = _fin_de(actual, tipo)
    dias_totales = (fin_actual - _inicio_de(actual, tipo)).days + 1
    dias_con_datos = (anchor - _inicio_de(actual, tipo)).days + 1
    dias_con_datos = max(1, min(dias_con_datos, dias_totales))
    completo = anchor >= fin_actual

    nota = None
    if not completo:
        nota = (
            f"El periodo actual está en curso: {dias_con_datos} de "
            f"{dias_totales} días. La comparación no está ajustada por días."
        )

    return {
        "disponible": True,
        "motivo": None,
        "tipo": tipo,
        "contra": contra,
        "actual": datos_actual,
        "referencia": datos_referencia,
        "completo": completo,
        "dias_con_datos": dias_con_datos,
        "dias_totales_periodo": dias_totales,
        "nota": nota,
        "variacion": {
            "unidades": datos_actual["unidades"] - datos_referencia["unidades"],
            "unidades_pct": _variacion(
                datos_actual["unidades"], datos_referencia["unidades"]
            ),
            "ingresos": round(
                datos_actual["ingresos"] - datos_referencia["ingresos"], 2
            ),
            "ingresos_pct": _variacion(
                datos_actual["ingresos"], datos_referencia["ingresos"]
            ),
            "num_ventas": datos_actual["num_ventas"] - datos_referencia["num_ventas"],
            "num_ventas_pct": _variacion(
                datos_actual["num_ventas"], datos_referencia["num_ventas"]
            ),
        },
    }
