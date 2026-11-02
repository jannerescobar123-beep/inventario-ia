"""Motor estadístico — Inventario-IA (semana 2).

Implementa, con pandas/numpy puros (explicable y sin dependencias pesadas):

- Rotación, días de cobertura y capital inmovilizado → RF-11, RF-12, RF-13, RF-17
- Predicción de demanda a 7/14/30 días              → RF-18, RF-19, RF-20
- Recomendaciones de compra (cuánto y cuándo)       → RF-22, RF-24, RF-25, RF-26
- Alertas: agotamiento, anomalías, baja rotación    → RF-12, RF-28, RF-29

Modelo de predicción (intencionalmente simple y explicable):

    demanda(fecha) = max(0, venta_diaria + pendiente·d) × factor_día_semana

- venta_diaria: promedio de los últimos 28 días
- pendiente: tendencia lineal de esos 28 días (limitada a ±3%/día para
  no extrapolar en locuras)
- factor_día_semana: estacionalidad semanal (media histórica de cada día
  de la semana relativa al promedio)
- Rango de confianza: esperado ± 1.28·σ_diaria·√días (≈ nivel 80%)

Cuando el negocio acumule más historia, migrar a Holt-Winters/ARIMA
(`statsforecast`, ya anotado en requirements.txt) sin cambiar el contrato.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alerta, Producto, Venta

# ── Parámetros del modelo (ajustables) ──────────────────────────────────────
DIAS_VENTANA = 90            # ventana de análisis histórica
DIAS_TENDENCIA = 28          # días para promedio/tendencia/estacionalidad
DIAS_MUERTO = 30             # sin ventas en N días → producto muerto (RF-12)
UMBRAL_BAJA_ROTACION = 0.5   # rotación del período bajo este valor → baja
LEAD_TIME_DEFECTO = 7        # días de reposición si no hay proveedor registrado
Z_ANOMALIA = 2.5             # |z| mínimo para marcar una semana como anómala
SEMANAS_ANOMALIA = 12        # semanas usadas para el z-score
MAX_ALERTAS_POR_TIPO = 20

_ORDEN_URGENCIA = {"critica": 0, "media": 1, "baja": 2}
_METRICA_VACIA = {
    "venta_diaria": 0.0,
    "desviacion": 0.0,
    "pendiente": 0.0,
    "factor_dow": {d: 1.0 for d in range(7)},
}


# ── Utilidades internas ─────────────────────────────────────────────────────
def _ventas_diarias(db: Session, dias: int) -> pd.DataFrame:
    """Series diarias por producto: index=producto_id, columnas=fechas (0 si no vendió)."""
    desde = date.today() - timedelta(days=dias - 1)
    filas = db.execute(
        select(Venta.producto_id, Venta.fecha, Venta.cantidad).where(Venta.fecha >= desde)
    ).all()
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas, columns=["producto_id", "fecha", "cantidad"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    diario = df.groupby(["producto_id", "fecha"])["cantidad"].sum().unstack(fill_value=0)
    rango = pd.date_range(pd.Timestamp(desde), pd.Timestamp(date.today()), freq="D")
    return diario.reindex(columns=rango, fill_value=0).fillna(0)


def _metricas_base(diario: pd.DataFrame) -> dict[int, dict]:
    """Calcula venta_diaria, desviación, pendiente y factor por día de semana."""
    metricas: dict[int, dict] = {}
    if diario.empty:
        return metricas

    reciente = diario.iloc[:, -DIAS_TENDENCIA:]
    venta_diaria = reciente.mean(axis=1)
    desviacion = reciente.std(axis=1).fillna(0.0)

    # Tendencia lineal por producto (limitada a ±3% del promedio diario)
    pendientes: dict[int, float] = {}
    if reciente.shape[1] >= 2:
        x = np.arange(reciente.shape[1], dtype=float)
        for pid, fila in reciente.iterrows():
            if float(fila.sum()) <= 0:
                continue
            ajuste = float(np.polyfit(x, fila.to_numpy(dtype=float), 1)[0])
            limite = 0.03 * float(venta_diaria[pid])
            pendientes[pid] = float(np.clip(ajuste, -limite, limite))

    # Estacionalidad semanal: media de cada día de la semana relativa al promedio
    transpuesta = reciente.T  # index=fechas, columnas=producto_id
    por_dow = transpuesta.groupby(transpuesta.index.day_of_week).mean()
    factores = (por_dow / venta_diaria.replace(0, np.nan)).fillna(1.0).clip(0.2, 3.0)

    for pid in diario.index:
        pid_int = int(pid)
        if pid in factores.columns:
            factor_dow = {int(d): float(v) for d, v in factores[pid].to_dict().items()}
        else:
            factor_dow = dict(_METRICA_VACIA["factor_dow"])
        metricas[pid_int] = {
            "venta_diaria": float(venta_diaria.get(pid, 0.0)),
            "desviacion": float(desviacion.get(pid, 0.0)),
            "pendiente": float(pendientes.get(pid, 0.0)),
            "factor_dow": factor_dow,
        }
    return metricas


def _pronostico(metrica: dict, dias: int) -> list[dict]:
    """Proyección día a día con el modelo explicado en el docstring."""
    hoy = pd.Timestamp(date.today())
    serie = []
    for offset in range(1, dias + 1):
        fecha_f = hoy + pd.Timedelta(days=offset)
        base = max(0.0, metrica["venta_diaria"] + metrica["pendiente"] * offset)
        esperado = base * metrica["factor_dow"].get(int(fecha_f.day_of_week), 1.0)
        serie.append({
            "offset": offset,
            "fecha": fecha_f.date().isoformat(),
            "esperado": round(float(esperado), 1),
        })
    return serie


# ── RF-11, RF-12, RF-13, RF-17: rotación y capital inmovilizado ────────────
def rotacion_productos(db: Session, dias: int = 90) -> dict:
    """Rotación por producto + clasificación normal / baja rotación / muerto."""
    productos = db.query(Producto).filter(Producto.activo == True).all()  # noqa: E712
    diario = _ventas_diarias(db, dias)
    metricas = _metricas_base(diario)
    unidades_totales = diario.sum(axis=1).to_dict() if not diario.empty else {}
    ultima_columna = diario.columns[-1] if not diario.empty else None

    registros = []
    for p in productos:
        metrica = metricas.get(p.id, _METRICA_VACIA)
        unidades = float(unidades_totales.get(p.id, 0.0))
        venta_diaria = metrica["venta_diaria"]

        dias_sin_venta = dias
        if not diario.empty and p.id in diario.index:
            posiciones = diario.loc[p.id].to_numpy().nonzero()[0]
            if len(posiciones):
                dias_sin_venta = int((ultima_columna - diario.columns[posiciones[-1]]).days)

        stock = float(p.stock_actual)
        rotacion = round(unidades / max(stock, 1.0), 2)
        cobertura = round(stock / venta_diaria, 1) if venta_diaria > 0 else None

        if dias_sin_venta >= DIAS_MUERTO:
            clasificacion = "muerto"
        elif rotacion < UMBRAL_BAJA_ROTACION:
            clasificacion = "baja_rotacion"
        else:
            clasificacion = "normal"

        registros.append({
            "producto_id": p.id,
            "nombre": p.nombre,
            "categoria": p.categoria,
            "stock_actual": stock,
            "costo": float(p.costo),
            "unidades_vendidas": unidades,
            "rotacion": rotacion,
            "venta_diaria": round(venta_diaria, 2),
            "dias_cobertura": cobertura,
            "dias_sin_venta": dias_sin_venta,
            "capital_inmovilizado": round(stock * float(p.costo), 2),
            "clasificacion": clasificacion,
        })

    registros.sort(key=lambda r: (r["rotacion"], -r["capital_inmovilizado"]))
    return {
        "parametros": {
            "dias": dias,
            "umbral_baja_rotacion": UMBRAL_BAJA_ROTACION,
            "dias_producto_muerto": DIAS_MUERTO,
        },
        "resumen": {
            "total_productos": len(registros),
            "en_baja_rotacion": sum(1 for r in registros if r["clasificacion"] == "baja_rotacion"),
            "muertos": sum(1 for r in registros if r["clasificacion"] == "muerto"),
            "capital_inmovilizado_total": round(
                sum(r["capital_inmovilizado"] for r in registros), 2
            ),
        },
        "productos": registros,
        "baja_rotacion": [r for r in registros if r["clasificacion"] == "baja_rotacion"],
        "muertos": [r for r in registros if r["clasificacion"] == "muerto"],
    }


# ── RF-18, RF-19, RF-20: predicción de demanda ──────────────────────────────
def predecir_demanda(db: Session, producto_id: int, dias: int = 7) -> dict:
    """Predicción de demanda de un producto a 7/14/30 días (ver ADR-001 fórmulas)."""
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise ValueError(f"El producto {producto_id} no existe")

    diario = _ventas_diarias(db, DIAS_VENTANA)
    base = {
        "producto_id": producto_id,
        "producto": producto.nombre,
        "dias": dias,
        "total_esperado": 0.0,
        "total_minimo": 0.0,
        "total_maximo": 0.0,
        "venta_diaria_promedio": 0.0,
        "confianza": "baja",
        "por_dia": [],
        "nota": "",
    }
    if diario.empty or producto_id not in diario.index:
        base["nota"] = (
            f"Sin ventas registradas en los últimos {DIAS_VENTANA} días: "
            "no es posible proyectar demanda."
        )
        return base

    metrica = _metricas_base(diario)[producto_id]
    serie = _pronostico(metrica, dias)
    total = sum(s["esperado"] for s in serie)
    margen_total = 1.28 * metrica["desviacion"] * math.sqrt(dias)

    por_dia = []
    for s in serie:
        margen_dia = 1.28 * metrica["desviacion"]
        por_dia.append({
            "fecha": s["fecha"],
            "esperado": s["esperado"],
            "minimo": round(max(0.0, s["esperado"] - margen_dia), 1),
            "maximo": round(s["esperado"] + margen_dia, 1),
        })

    dias_con_datos = int((diario.loc[producto_id] > 0).sum())
    confianza = "alta" if dias_con_datos >= 56 else ("media" if dias_con_datos >= 14 else "baja")

    if metrica["pendiente"] > 0.01 * max(metrica["venta_diaria"], 0.01):
        tendencia = "al alza"
    elif metrica["pendiente"] < -0.01 * max(metrica["venta_diaria"], 0.01):
        tendencia = "a la baja"
    else:
        tendencia = "estable"

    base.update({
        "total_esperado": round(total, 1),
        "total_minimo": round(max(0.0, total - margen_total), 1),
        "total_maximo": round(total + margen_total, 1),
        "venta_diaria_promedio": round(metrica["venta_diaria"], 2),
        "confianza": confianza,
        "por_dia": por_dia,
        "nota": (
            f"Basado en {dias_con_datos} días con ventas de los últimos {DIAS_VENTANA}. "
            f"Promedio de {metrica['venta_diaria']:.1f} u./día, tendencia {tendencia}. "
            "El rango mínimo–máximo cubre el ~80% de los escenarios probables."
        ),
    })
    return base


# ── RF-22, RF-24, RF-25, RF-26: recomendaciones de compra ───────────────────
def recomendaciones_compra(db: Session) -> dict:
    """Lista de compra sugerida: qué comprar, cuánto, cuándo y por qué.

    Fórmulas:
        punto_reorden   = venta_diaria × lead_time + stock_minimo
        cantidad        = max(0, ⌈max(demanda_14d + stock_minimo,
                                        venta_diaria × (lead_time + 7)) − stock⌉)
        urgencia        = crítica si cobertura ≤ lead_time o stock ≤ mínimo
    """
    productos = db.query(Producto).filter(Producto.activo == True).all()  # noqa: E712
    diario = _ventas_diarias(db, DIAS_VENTANA)
    metricas = _metricas_base(diario)
    lead = LEAD_TIME_DEFECTO

    items = []
    for p in productos:
        metrica = metricas.get(p.id, _METRICA_VACIA)
        vd = metrica["venta_diaria"]
        stock = float(p.stock_actual)
        smin = float(p.stock_minimo)

        punto_reorden = vd * lead + smin
        necesita = (vd > 0 and stock < punto_reorden) or (smin > 0 and stock < smin)
        if not necesita:
            continue

        demanda_14 = sum(s["esperado"] for s in _pronostico(metrica, 14))
        cobertura = stock / vd if vd > 0 else None
        objetivo = max(demanda_14 + smin, vd * (lead + 7)) if vd > 0 else smin
        cantidad = int(math.ceil(max(objetivo - stock, 0.0)))
        if cantidad <= 0:
            continue

        if cobertura is not None:
            urgencia = (
                "critica"
                if (cobertura <= lead or (smin > 0 and stock <= smin))
                else ("media" if cobertura <= lead + 7 else "baja")
            )
        else:
            urgencia = "critica" if (smin > 0 and stock <= smin) else "baja"

        if urgencia == "critica":
            fecha_sugerida = date.today().isoformat()
        elif vd > 0:
            dias_espera = max(0.0, (stock - punto_reorden) / vd)
            fecha_sugerida = (date.today() + timedelta(days=round(dias_espera))).isoformat()
        else:
            fecha_sugerida = None

        if cobertura is not None:
            contexto_stock = f"tienes {cobertura:.0f} días de cobertura"
        else:
            contexto_stock = "no registra movimiento reciente"

        items.append({
            "producto_id": p.id,
            "producto": p.nombre,
            "categoria": p.categoria,
            "stock_actual": stock,
            "stock_minimo": smin,
            "venta_diaria": round(vd, 2),
            "demanda_14d": round(demanda_14, 1),
            "dias_cobertura": round(cobertura, 1) if cobertura else None,
            "punto_reorden": round(punto_reorden, 1),
            "cantidad_sugerida": cantidad,
            "urgencia": urgencia,
            "fecha_sugerida": fecha_sugerida,
            "costo_estimado": round(cantidad * float(p.costo), 2),
            "motivo": (
                f"Vendes ~{vd:.1f} u./día y {contexto_stock} con {stock:.0f} en stock; "
                f"el proveedor tarda ~{lead} días. Conviene pedir {cantidad} u. "
                f"para cubrir 2 semanas de venta y mantener tu mínimo ({smin:.0f})."
            ),
        })

    items.sort(key=lambda i: (_ORDEN_URGENCIA[i["urgencia"]], i["dias_cobertura"] or 9e9))
    return {
        "generado": datetime.utcnow().isoformat(),
        "parametros": {"lead_time_dias": lead, "dias_objetivo": 14},
        "resumen": {
            "total_items": len(items),
            "criticos": sum(1 for i in items if i["urgencia"] == "critica"),
            "medios": sum(1 for i in items if i["urgencia"] == "media"),
            "bajos": sum(1 for i in items if i["urgencia"] == "baja"),
            "costo_estimado_total": round(sum(i["costo_estimado"] for i in items), 2),
        },
        "productos": items,
    }


# ── RF-12, RF-28, RF-29: alertas automáticas ────────────────────────────────
def detectar_anomalias(db: Session) -> list[dict]:
    """Picos o caídas inusuales de la última semana (z-score vs. 12 semanas)."""
    diario = _ventas_diarias(db, SEMANAS_ANOMALIA * 7)
    if diario.empty:
        return []
    semanal = diario.T.resample("W").sum()
    if len(semanal) < 4:
        return []

    resultados = []
    for pid in semanal.columns:
        serie = semanal[pid]
        if (serie > 0).sum() < 8:
            continue
        media = float(serie.iloc[:-1].mean())
        std = float(serie.iloc[:-1].std())
        if std <= 0 or media <= 0:
            continue
        z = float((serie.iloc[-1] - media) / std)
        if abs(z) < Z_ANOMALIA:
            continue
        producto = db.get(Producto, int(pid))
        nombre = producto.nombre if producto else f"producto {pid}"
        tipo = "pico" if z > 0 else "caída"
        resultados.append({
            "producto_id": int(pid),
            "producto": nombre,
            "semana": semanal.index[-1].date().isoformat(),
            "unidades_semana": float(serie.iloc[-1]),
            "media_semanal": round(media, 1),
            "z": round(z, 2),
            "severidad": "media",
            "mensaje": (
                f"'{nombre}' vendió {serie.iloc[-1]:.0f} u. la semana pasada frente a una "
                f"media de {media:.0f} → {tipo} inusual (z={z:.1f}). Revisa si hubo "
                "promoción, un evento o un error de registro."
            ),
        })
    return resultados[:MAX_ALERTAS_POR_TIPO]


def generar_alertas(db: Session) -> int:
    """Regenera las alertas automáticas del negocio (agotamiento, muertos, anomalías).

    Se ejecuta al consultar GET /api/alertas: borra las alertas automáticas
    anteriores y crea las vigentes con los datos actuales.
    """
    tipos = ("riesgo_agotamiento", "baja_rotacion", "anomalia_ventas")
    db.query(Alerta).filter(Alerta.tipo.in_(tipos)).delete(synchronize_session=False)
    hoy = datetime.utcnow()
    nuevas: list[Alerta] = []

    # 1) Riesgo de agotamiento (ítems críticos de la lista de compra)
    try:
        recomendaciones = recomendaciones_compra(db)
        criticos = [i for i in recomendaciones["productos"] if i["urgencia"] == "critica"]
        for item in criticos[:MAX_ALERTAS_POR_TIPO]:
            mensaje = (
                f"'{item['producto']}' se agota pronto: {item['dias_cobertura'] or 0} días "
                f"de cobertura con {item['stock_actual']:.0f} en stock. "
                f"Sugerido: comprar {item['cantidad_sugerida']} u. ya."
            )
            nuevas.append(Alerta(tipo="riesgo_agotamiento", severidad="critica",
                                 producto_id=item["producto_id"], mensaje=mensaje, fecha=hoy))
    except Exception:
        pass  # las demás alertas no deben fallar por un error de recomendaciones

    # 2) Productos muertos: dinero inmovilizado (RF-12)
    try:
        rotacion = rotacion_productos(db)
        for r in rotacion["muertos"][:MAX_ALERTAS_POR_TIPO]:
            mensaje = (
                f"'{r['nombre']}' lleva {r['dias_sin_venta']} días sin ventas y tiene "
                f"${r['capital_inmovilizado']:.2f} inmovilizados en stock "
                f"({r['stock_actual']:.0f} u.). Considera liquidación o dejar de comprarlo."
            )
            nuevas.append(Alerta(tipo="baja_rotacion", severidad="baja",
                                 producto_id=r["producto_id"], mensaje=mensaje, fecha=hoy))
    except Exception:
        pass

    # 3) Anomalías semanales (RF-29)
    for a in detectar_anomalias(db):
        nuevas.append(Alerta(tipo="anomalia_ventas", severidad=a["severidad"],
                             producto_id=a["producto_id"], mensaje=a["mensaje"], fecha=hoy))

    db.add_all(nuevas)
    db.commit()
    return len(nuevas)
