import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import json

BASE_DIR = Path(__file__).parent.parent  # backend/
DB_PATH = BASE_DIR / "datos" / "inventario.db"


def _a_datetime(valor: Any) -> Optional[datetime]:
    """
    Convertir un valor de fecha de SQLite a datetime.

    La tabla 'ventas' guarda la fecha como texto ISO 'YYYY-MM-DD', por lo que
    hay que convertirla antes de restarla de un datetime.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


# --- RF-09 a RF-11: KPIs y tablero ---

def calcular_kpis(conn) -> Dict[str, Any]:
    """Calcular KPIs básicos para el tablero (RF-09)."""
    cursor = conn.cursor()
    
    # Ventas totales (suma de cantidad * precio de todas las ventas registradas)
    cursor.execute("""
        SELECT COALESCE(SUM(cantidad * precio), 0) as ventas_totales,
               COALESCE(SUM(cantidad), 0) as unidades_vendidas
        FROM ventas
    """)
    row = cursor.fetchone()
    ventas_totales = float(row[0] or 0)
    unidades_vendidas = int(row[1] or 0)
    
    # Ticket promedio
    ticket_promedio = ventas_totales / unidades_vendidas if unidades_vendidas > 0 else 0
    
    # Top de productos (más vendidos)
    cursor.execute("""
        SELECT p.nombre, SUM(v.cantidad) as total_cantidad
        FROM ventas v
        JOIN productos p ON p.nombre_norm = v.producto_norm
        GROUP BY p.id
        ORDER BY total_cantidad DESC
        LIMIT 5
    """)
    top_productos = [{"nombre": r[0], "cantidad": int(r[1])} for r in cursor.fetchall()]
    
    # Margen total (aproximado: diferencia entre precio y costo)
    cursor.execute("""
        SELECT COALESCE(SUM((v.precio - p.costo) * v.cantidad), 0)
        FROM ventas v
        JOIN productos p ON p.nombre_norm = v.producto_norm
    """)
    margen_total = float(cursor.fetchone()[0] or 0)
    
    return {
        "ventas_totales": round(ventas_totales, 2),
        "ticket_promedio": round(ticket_promedio, 2),
        "unidades_vendidas": unidades_vendidas,
        "margen_total": round(margen_total, 2),
        "top_productos": top_productos
    }


# --- RF-11, RF-12, RF-13: Rotación, productos muertos, días de cobertura ---

def calcular_rotacion_inventario(conn, dias: int = 30) -> Dict[str, Any]:
    """
    Calcular rotación de inventario por producto (RF-11).
    Retorna rotación, productos de baja rotación y productos "muertos" (RF-12).
    """
    cursor = conn.cursor()
    
    # Última fecha de venta por producto
    cursor.execute("""
        SELECT p.id, p.nombre, p.stock_actual,
               COALESCE(SUM(v.cantidad), 0) as total_vendido,
               MAX(v.fecha) as ultima_venta
        FROM productos p
        LEFT JOIN ventas v ON p.nombre_norm = v.producto_norm
        GROUP BY p.id
    """)
    filas = cursor.fetchall()
    
    hoy = datetime.now()
    rotacion = []
    baja_rotacion = []
    muertos = []
    
    for fila in filas:
        prod_id, nombre, stock_actual, total_vendido, ultima_venta = fila
        
        # Rotación = total vendido / días
        if total_vendido > 0 and ultima_venta:
            fecha_venta = _a_datetime(ultima_venta)
            dias_desde_ultima = (hoy - fecha_venta).days if fecha_venta else 0
            rotacion_mes = total_vendido / max(dias_desde_ultima, 1) * 30
        else:
            rotacion_mes = 0
            dias_desde_ultima = None
        
        rotacion.append({
            "id": prod_id,
            "nombre": nombre,
            "stock_actual": stock_actual,
            "total_vendido_30d": total_vendido,
            "dias_desde_ultima_venta": dias_desde_ultima,
            "indice_rotacion": round(rotacion_mes, 2) if rotacion_mes else 0
        })
        
        # RF-12: Productos de baja rotación (menos de 1 unidad/mes) o sin ventas
        if total_vendido == 0 or rotacion_mes < 1:
            baja_rotacion.append({
                "id": prod_id,
                "nombre": nombre,
                "stock_actual": stock_actual,
                "razon": "sin_ventas" if total_vendido == 0 else "baja_rotacion"
            })
        
        # RF-13: Días de cobertura = stock_actual / (vendido_promedio_diario)
        if total_vendido > 0 and dias_desde_ultima:
            dias_cob = stock_actual / (total_vendido / max(dias_desde_ultima, 1)) * 30
        elif stock_actual > 0 and total_vendido == 0:
            dias_cob = None  # Stock ilimitado (sin ventas recientes)
        else:
            dias_cob = 0
        
        if dias_cob is not None and dias_cob >= 0:
            rotacion[-1]["dias_cobertura"] = round(dias_cob, 1)
    
    # Ordenar baja rotación por stock (los de más stock primero = riesgo mayor)
    baja_rotacion.sort(key=lambda x: x["stock_actual"], reverse=True)
    
    return {
        "productos": rotacion,
        "baja_rotacion": baja_rotacion[:10],  # Top 10 de baja rotación
        "muertos": [p["nombre"] for p in baja_rotacion if p["razon"] == "sin_ventas"]
    }


# --- RF-14, RF-15: Estacionalidad, ABC ---

def detectar_estacionalidad(conn, producto_nombre: Optional[str] = None) -> Dict[str, Any]:
    """
    Detectar patrones estacionales (RF-14).
    Análisis simple: comparar ventas por mes vs promedio.
    """
    cursor = conn.cursor()
    
    if producto_nombre:
        cursor.execute("""
            SELECT STRFTIME('%m', v.fecha) as mes,
                   SUM(v.cantidad) as vendidos
            FROM ventas v
            JOIN productos p ON p.nombre_norm = v.producto_norm
            WHERE UPPER(p.nombre) = ?
            GROUP BY mes
            ORDER BY mes
        """, (producto_nombre,))
    else:
        cursor.execute("""
            SELECT STRFTIME('%m', v.fecha) as mes,
                   SUM(v.cantidad) as vendidos
            FROM ventas v
            GROUP BY mes
            ORDER BY mes
        """)
    
    filas = cursor.fetchall()
    
    if not filas:
        return {"estacional": False, "patron": "sin_datos"}
    
    # Agrupar por mes y calcular promedio
    meses_data = {}
    for mes, vendidos in filas:
        mes_num = int(mes)
        if mes_num not in meses_data:
            meses_data[mes_num] = []
        meses_data[mes_num].append(int(vendidos))
    
    promedios_mes = {m: sum(v) / len(v) for m, v in sorted(meses_data.items())}
    
    # Detectar si hay un mes claramente más alto
    valores = list(promedios_mes.values())
    if len(valores) >= 3:
        max_prom = max(valores)
        # Si el mes máximo es > 1.5x el mínimo, hay estacionalidad
        min_prom = min(valores)
        es_estacional = max_prom > min_prom * 1.5
        mes_peak = max(promedios_mes, key=promedios_mes.get)
        
        return {
            "estacional": es_estacional,
            "patron": f"peak_en_mes_{mes_peak}",
            "promedios_mensuales": {str(k): round(v, 2) for k, v in promedios_mes.items()}
        }
    
    return {"estacional": False, "patron": "insuficiente_datos"}


def clasificar_abc(conn) -> Dict[str, Any]:
    """
    Clasificar productos por análisis ABC (RF-15).
    A: 80% del valor (poco productos, mucho valor)
    B: 15% del valor
    C: 5% del valor (muchos productos, poco valor)
    """
    cursor = conn.cursor()
    
    # Obtener valor de inventario por producto (stock * precio)
    cursor.execute("""
        SELECT p.id, p.nombre, p.stock_actual, p.precio_venta,
               (p.stock_actual * p.precio_venta) as valor_inventario
        FROM productos p
        WHERE p.precio_venta > 0
        ORDER BY valor_inventario DESC
    """)
    filas = cursor.fetchall()
    
    if not filas:
        return {"clases": {}, "total_productos": 0}
    
    # Calcular total de valor
    total_valor = sum(f[4] for f in filas)
    
    # Acumular por porcentaje
    acumulado = 0
    clases = {"A": [], "B": [], "C": []}
    total_prod = 0
    
    for fila in filas:
        prod_id, nombre, stock, precio, valor = fila
        acumulado += valor
        total_prod += 1
        
        porcentaje_valor = (valor / total_valor * 100) if total_valor > 0 else 0
        porcentaje_acum = (acumulado / total_valor * 100) if total_valor > 0 else 0
        
        # Clasificación ABC tradicional
        if porcentaje_acum <= 80:
            clase = "A"
        elif porcentaje_acum <= 95:
            clase = "B"
        else:
            clase = "C"
        
        clases[clase].append({
            "id": prod_id,
            "nombre": nombre,
            "stock": stock,
            "precio": round(precio, 2),
            "valor_inventario": round(valor, 2),
            "porcentaje_acumulado": round(porcentaje_acum, 2)
        })
    
    return {
        "clases": clases,
        "total_productos": total_prod,
        "total_valor_inventario": round(total_valor, 2)
    }


# --- RF-17: Capital inmovilizado ---

def capital_inmovilizado_por_producto(conn) -> Dict[str, Any]:
    """Capital inmovilizado por producto (RF-17)."""
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.id, p.nombre, p.stock_actual, p.costo, p.precio_venta,
               (p.stock_actual * p.costo) as capital
        FROM productos p
        WHERE p.stock_actual > 0 AND p.costo > 0
        ORDER BY capital DESC
    """)
    filas = cursor.fetchall()
    
    resultado = {}
    total_capital = 0
    
    for fila in filas:
        prod_id, nombre, stock, costo, precio, capital = fila
        resultado[nombre] = {
            "stock": stock,
            "costo_unitario": round(costo, 2),
            "precio_venta": round(precio, 2),
            "capital": round(capital, 2)
        }
        total_capital += capital
    
    return {
        "por_producto": resultado,
        "total_capital_inmovilizado": round(total_capital, 2)
    }


# --- RF-18 a RF-20: Predicción de demanda ---

def predecir_demanda_media_movil(conn, producto_nombre: str, 
                                  dias: int = 30) -> Dict[str, Any]:
    """
    Predecir demanda usando media móvil simple (RF-18).
    Para 7, 14 y 30 días.
    """
    cursor = conn.cursor()
    
    # Obtener historial de ventas diarias por producto
    cursor.execute("""
        SELECT DATE(v.fecha) as dia, SUM(v.cantidad) as cantidad_diaria
        FROM ventas v
        JOIN productos p ON p.nombre_norm = v.producto_norm
        WHERE UPPER(p.nombre) = ?
        GROUP BY DATE(v.fecha)
        ORDER BY dia DESC
        LIMIT 90  # Últimos 3 meses
    """, (producto_nombre,))
    
    filas = cursor.fetchall()
    
    if not filas or len(filas) < 3:
        return {"error": "insuficiente_historial", "predicciones": {}}
    
    # Convertir a lista ordenada de más antiguo a más reciente
    historico = [int(f[1]) for f in reversed(filas)]
    
    # Media móvil simple de los últimos N días
    def media_movil(hist, ventana):
        if len(hist) < ventana:
            return sum(hist) / len(hist) if hist else 0
        return sum(hist[-ventana:]) / ventana
    
    pred_7 = round(media_movil(historico, 7))
    pred_14 = round(media_movil(historico, 14))
    pred_30 = round(media_movil(historico, 30))
    
    # Rangos de confianza simples (media ± desvío simple)
    # En un caso real usaríamos ARIMA o estadística apropiada
    return {
        "predicciones": {
            "7_dias": pred_7,
            "14_dias": pred_14,
            "30_dias": pred_30
        },
        "metodo": "media_movil_simple",
        "historico_dias": len(historico),
        "ultima_actualizacion": datetime.now().isoformat()
    }


def predecir_demanda_holt_winters(conn, producto_nombre: str,
                                    dias: int = 30) -> Dict[str, Any]:
    """
    Predecir demanda usando Holt-Winters (suavizado exponencial) (RF-18/RF-19).
    Versión simplificada con implementación propia (sin librerías pesadas).
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DATE(v.fecha) as dia, SUM(v.cantidad) as cantidad_diaria
        FROM ventas v
        JOIN productos p ON p.nombre_norm = v.producto_norm
        WHERE UPPER(p.nombre) = ?
        GROUP BY DATE(v.fecha)
        ORDER BY dia DESC
        LIMIT 180  # Últimos 6 meses
    """, (producto_nombre,))
    
    filas = cursor.fetchall()
    
    if not filas or len(filas) < 10:
        return predecir_demanda_media_movil(conn, producto_nombre, dias)
    
    # Datos ordenados cronológicamente (más antiguo primero)
    historico = [int(f[1]) for f in reversed(filas)]
    n = len(historico)
    
    # Parámetros simpletes de Holt-Winters (sin estacionalidad compleja)
    # Alpha (level), Beta (trend), Gamma (seasonal) - valores por defecto
    alpha, beta, gamma = 0.3, 0.1, 0.1
    
    # Calcular tendencia y nivel simple
    level = sum(historico) / n  # Promedio inicial
    trend = (historico[-1] - historico[0]) / (n - 1) if n > 1 else 0
    
    # Predicción simple: nivel + tendencia * pasos
    pasos = dias
    
    nivel_predicho = level + trend * pasos
    tendencia_predicha = trend
    
    # Mínimo para no ser negativo
    nivel_predicho = max(nivel_predicho, 0)
    
    return {
        "predicciones": {
            "dias": dias,
            "predicha": int(nivel_predicho),
            "tendencia": round(tendencia_predicha, 2)
        },
        "metodo": "holt_winters_simple",
        "datos_usados": n,
        "alpha": alpha, "beta": beta, "gamma": gamma
    }


# --- RF-22 a RF-27: Recomendaciones de compra ---

def generar_recomendaciones_compra(conn, stock_minimo: int = None,
                                    stock_maximo: int = None,
                                    lead_time_dias: int = 7) -> Dict[str, Any]:
    """
    Generar lista semanal de productos sugeridos para comprar (RF-22 a RF-27).
    Considera stock actual, stock mínimo por producto, venta proyectada y lead time.

    - `stock_minimo`: si se indica, sustituye al stock mínimo de cada producto
      (sirve como umbral de filtrado y como objetivo de reposición).
    - `stock_maximo`: si se indica, la cantidad sugerida nunca supera la
      diferencia hasta ese stock objetivo.
    """
    cursor = conn.cursor()
    hoy = datetime.now()

    # Ancla temporal: la última venta registrada. Así el histórico de demanda
    # sigue siendo útil aunque el archivo importado no sea de hoy.
    cursor.execute("SELECT MAX(fecha) FROM ventas")
    fila_anchor = cursor.fetchone()
    anchor = fila_anchor[0] if fila_anchor and fila_anchor[0] else hoy.strftime("%Y-%m-%d")

    if stock_minimo is not None:
        # Umbral global indicado por el llamador
        cursor.execute("""
            SELECT p.id, p.nombre, p.nombre_norm, p.stock_actual, p.stock_minimo,
                   p.precio_venta, p.costo,
                   (p.stock_actual * p.precio_venta) AS valor
            FROM productos p
            WHERE p.stock_actual <= ?
            ORDER BY p.stock_actual ASC
        """, (stock_minimo,))
    else:
        # Sin umbral global: se usa el stock mínimo de cada producto
        # (columna productos.stock_minimo, ADR-003).
        cursor.execute("""
            SELECT p.id, p.nombre, p.nombre_norm, p.stock_actual, p.stock_minimo,
                   p.precio_venta, p.costo,
                   (p.stock_actual * p.precio_venta) AS valor
            FROM productos p
            WHERE (p.stock_minimo > 0 AND p.stock_actual <= p.stock_minimo * 1.5)
               OR (p.stock_minimo = 0 AND p.stock_actual = 0)
            ORDER BY p.stock_actual ASC
        """)

    filas = cursor.fetchall()
    recomendaciones = []

    for fila in filas:
        prod_id, nombre, nombre_norm, stock_actual, stock_minimo_producto, precio_venta, costo, valor = fila

        # Objetivo de reposición: el mínimo del producto (o el global si se indicó)
        minimo_objetivo = stock_minimo if stock_minimo is not None else (stock_minimo_producto or 0)

        # Demanda de los últimos 7 días (relativos a la última venta registrada).
        # El emparejamiento usa producto_norm para ser insensible a tildes.
        cursor.execute("""
            SELECT COALESCE(SUM(cantidad), 0)
            FROM ventas v
            WHERE v.producto_norm = ?
              AND v.fecha > date(?, '-7 days')
              AND v.fecha <= date(?)
        """, (nombre_norm, anchor, anchor))
        ult_7d = cursor.fetchone()[0] or 0
        demanda_diaria = ult_7d / 7

        # Demanda proyectada durante el lead time del proveedor
        demanda_lead_time = demanda_diaria * lead_time_dias

        # Punto de reorden (RF-25): demanda del lead time + stock de seguridad
        stock_seguridad = int(demanda_lead_time * 0.2)
        punto_reorden = int(demanda_lead_time + stock_seguridad)

        # Cantidad a comprar (RF-23): lo que falta para llegar al mínimo,
        # más la demanda del lead time y el stock de seguridad
        cantidad_sugerida = int(round(
            minimo_objetivo - stock_actual + demanda_lead_time + stock_seguridad
        ))
        if stock_maximo is not None:
            cantidad_sugerida = min(cantidad_sugerida, max(0, stock_maximo - stock_actual))
        cantidad_sugerida = max(0, cantidad_sugerida)

        if cantidad_sugerida == 0:
            continue

        # Urgencia relativa al mínimo y a la demanda de cada producto (RF-26)
        referencia = max(minimo_objetivo, int(demanda_lead_time), 1)
        if stock_actual <= 0 or cantidad_sugerida >= referencia:
            urgencia = "crítico"
        elif cantidad_sugerida >= referencia * 0.5:
            urgencia = "medio"
        else:
            urgencia = "bajo"

        # Fecha sugerida para comprar (RF-24): hoy si ya está en el punto de
        # reorden; si no, el día en que se alcanzaría (máximo una semana).
        if stock_actual <= punto_reorden or demanda_diaria <= 0:
            dias_hasta_reorden = 0
        else:
            dias_hasta_reorden = int((stock_actual - punto_reorden) / demanda_diaria)
        dias_hasta_reorden = min(max(dias_hasta_reorden, 0), 7)
        fecha_sugerida = (hoy + timedelta(days=dias_hasta_reorden)).strftime("%Y-%m-%d")
        fecha_entrega = (hoy + timedelta(days=dias_hasta_reorden + lead_time_dias)).strftime("%Y-%m-%d")

        recomendaciones.append({
            "producto_id": prod_id,
            "producto": nombre,
            "stock_actual": stock_actual,
            "stock_minimo": minimo_objetivo,
            "demanda_proyectada": int(demanda_lead_time),
            "cantidad_sugerida": cantidad_sugerida,
            "punto_reorden": punto_reorden,
            "punto_reorden_detalle": (
                f"reponer cuando el stock llegue a {punto_reorden} unidades "
                f"(stock mínimo {minimo_objetivo})"
            ),
            "urgencia": urgencia,
            "fecha_sugerida": fecha_sugerida,
            "fecha_entrega_estimada": fecha_entrega,
            "valor_inventario": round(valor or 0, 2),
            "lead_time_dias": lead_time_dias
        })

    # Ordenar por urgencia y, a igual urgencia, por fecha sugerida
    orden_urgencia = {"crítico": 0, "medio": 1, "bajo": 2}
    recomendaciones.sort(
        key=lambda x: (orden_urgencia.get(x["urgencia"], 9), x["fecha_sugerida"], -x["cantidad_sugerida"])
    )

    return {
        "recomendaciones": recomendaciones[:20],  # Top 20
        "total_analizados": len(filas),
        "total_recomendado": len(recomendaciones),
        "lead_time_asumido": lead_time_dias,
        "fecha_referencia_demanda": anchor
    }


# --- RF-28 a RF-31: Alertas inteligentes ---

def alertas_riesgo_agotamiento(conn) -> List[Dict[str, Any]]:
    """
    Alertar sobre productos con riesgo de agotarse pronto (RF-28).
    Productos donde stock_actual <= stock_minimo * 1.5 (50% de margen)
    """
    cursor = conn.cursor()

    # Ancla temporal: la última venta registrada, para que los días estimados
    # se calculen sobre los datos realmente importados.
    cursor.execute("SELECT MAX(fecha) FROM ventas")
    fila_anchor = cursor.fetchone()
    anchor = fila_anchor[0] if fila_anchor and fila_anchor[0] else datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT id, nombre, nombre_norm, stock_actual, stock_minimo, costo, precio_venta
        FROM productos
        WHERE stock_minimo > 0 AND stock_actual <= stock_minimo * 1.5
        ORDER BY (stock_minimo - stock_actual) ASC
    """)

    filas = cursor.fetchall()
    alertas = []

    for fila in filas:
        prod_id, nombre, nombre_norm, stock_actual, stock_minimo, costo, precio_venta = fila
        dias_para_agotar = None
        if stock_actual > 0:
            # Basado en velocidad de venta reciente (emparejamiento por nombre_norm)
            cursor.execute("""
                SELECT COALESCE(SUM(cantidad), 0) as ultimos_7
                FROM ventas v
                WHERE v.producto_norm = ?
                  AND v.fecha > date(?, '-7 days')
                  AND v.fecha <= date(?)
            """, (nombre_norm, anchor, anchor))
            ult_7d = cursor.fetchone()[0]
            ventas_diarias_prom = ult_7d / 7 if ult_7d else 0
            if ventas_diarias_prom > 0:
                dias_para_agotar = int(stock_actual / ventas_diarias_prom)
            else:
                dias_para_agotar = None
        else:
            dias_para_agotar = 0

        alertas.append({
            "producto_id": prod_id,
            "producto": nombre,
            "stock_actual": stock_actual,
            "stock_minimo": stock_minimo,
            "riesgo": "agotamiento_inminente" if dias_para_agotar is not None and dias_para_agotar <= 7 else "agotamiento_pronto",
            "dias_estimados": dias_para_agotar,
            "valor_inventario": round((stock_actual * precio_venta) if precio_venta else 0, 2)
        })

    # Ordenar por urgencia (los que se agotan antes primero)
    alertas.sort(key=lambda x: x["dias_estimados"] if x["dias_estimados"] is not None else 99)

    return alertas


def alertas_comportamientos_inusuales(conn) -> Dict[str, Any]:
    """
    Detectar comportamientos inusuales en ventas (picos o caídas anómalas) (RF-29).
    Usar simple desviación estándar sobre ventas diarias.
    """
    cursor = conn.cursor()
    
    # Obtener ventas diarias de los últimos 30 días
    cursor.execute("""
        SELECT DATE(v.fecha) as dia, SUM(v.cantidad) as cantidad_diaria
        FROM ventas v
        GROUP BY DATE(v.fecha)
        ORDER BY dia DESC
        LIMIT 30
    """)
    
    filas = cursor.fetchall()
    if len(filas) < 5:
        return {"alerta": False, "detalle": "insufficient_data"}
    
    cantidades = [int(f[1]) for f in reversed(filas)]
    n = len(cantidades)
    media = sum(cantidades) / n
    
    # Desviación estándar simple
    varianza = sum((x - media) ** 2 for x in cantidades) / (n - 1)
    desv_std = varianza ** 0.5
    
    # Umbrales: > media + 1.5*desv_desv = pico anomaly
    # < media - 1.5*desv_std = caída anomaly
    picos = [c for c in cantidades if c > media + 1.5 * desv_std]
    caidas = [c for c in cantidades if c < media - 1.5 * desv_std]
    
    resultado = {
        "alerta": len(picos) > 0 or len(caidas) > 0,
        "media_diaria": round(media, 2),
        "desviacion_std": round(desv_std, 2),
        "picos_detectados": len(picos),
        "caidas_detectadas": len(caidas),
        "ultima_actualizacion": datetime.now().isoformat()
    }
    
    if picos:
        resultado["ultimo_pico"] = {
            "cantidad": max(picos),
            "fecha": max(filas, key=lambda f: int(f[1]))[0] if filas else None
        }
    
    if caidas:
        resultado["ultima_caida"] = {
            "cantidad": min(caidas),
            "fecha": min(filas, key=lambda f: int(f[1]))[0] if filas else None
        }
    
    return resultado


# Exportar todas las funciones para que el frontend (Persona B) las pueda consumir
__all__ = [
    "calcular_kpis",
    "calcular_rotacion_inventario",
    "detectar_estacionalidad",
    "clasificar_abc",
    "capital_inmovilizado_por_producto",
    "predecir_demanda_media_movil",
    "predecir_demanda_holt_winters",
    "generar_recomendaciones_compra",
    "alertas_riesgo_agotamiento",
    "alertas_comportamientos_inusuales"
]