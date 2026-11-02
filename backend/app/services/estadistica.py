"""Motor estadístico — TODO(Persona A), semana 2 del roadmap.

Cada función se implementa sobre SQLite y se consume desde
app/routers/analisis.py. Mientras devuelvan NotImplementedError, la API
responde con `estado: "pendiente"` (el frontend ya está preparado).

Fórmulas de referencia (docs/ARQUITECTURA.md):

- Rotación            = unidades vendidas (90 días) / stock promedio
- Días de cobertura   = stock_actual / venta diaria promedio
- Punto de reorden    = venta diaria promedio × lead_time + stock de seguridad
- Predicción          = media móvil → Holt (suavizado exponencial) → ARIMA
- Anomalías           = z-score de ventas semanales; alerta si |z| > 3
"""
from sqlalchemy.orm import Session


def rotacion_productos(db: Session, dias: int = 90) -> dict:
    """Rotación por producto + lista de productos de baja rotación/muertos.

    Debe devolver:
        {"productos": [{nombre, categoria, unidades, rotacion, dias_sin_venta}],
         "baja_rotacion": [...], "muertos": [...]}
    """
    raise NotImplementedError


def predecir_demanda(db: Session, producto_id: int, dias: int = 7) -> dict:
    """Predicción de demanda por producto a 7/14/30 días.

    Debe devolver:
        {"producto": ..., "total_esperado": ...,
         "por_dia": [{fecha, esperado, minimo, maximo}], "confianza": ...}
    Sugerencia: empezar con media móvil de 14 días, luego Holt-Winters
    con `statsforecast` (ya está comentado en requirements.txt).
    """
    raise NotImplementedError


def recomendaciones_compra(db: Session) -> dict:
    """Lista de compra sugerida de la semana.

    Cantidad sugerida = demanda proyectada + stock de seguridad - stock_actual
    (nunca negativa), priorizada por urgencia según días de cobertura
    y lead time del proveedor.
    """
    raise NotImplementedError


def detectar_anomalias(db: Session) -> list[dict]:
    """Picos o caídas inusuales en ventas (z-score semanal, |z| > 3).

    Cada anomalía debe generar además una fila en la tabla `alertas`.
    """
    raise NotImplementedError
