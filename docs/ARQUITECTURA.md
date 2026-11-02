# Arquitectura — Inventario-IA

> Estado: ✅ Aceptada (ver ADR-001 en `inventario-ia-docs/decisiones/`)

## Visión general

Aplicación **local tipo "web local"**: el backend Python sirve una API REST que consume un
frontend React. Todo corre en el PC del negocio, sin internet y sin nube.

| Capa | Tecnología | Por qué |
|---|---|---|
| Núcleo | **Python 3.11+** | Ecosistema estadístico único (pandas, statsmodels, statsforecast) |
| Base de datos | **SQLite** | Un solo archivo, cero configuración, ideal para PyME offline |
| API | **FastAPI** | Rápida de construir, documentación automática (`/docs`), fácil de empaquetar |
| UI | **React + Vite** | Prototipado veloz de dashboards; gráficos con Recharts |
| IA local | **Ollama** (llama3.2:3b) | Corre en 8 GB RAM sin GPU, API OpenAI-compatible, function calling |
| Distribución futura | pywebview / Tauri | Envolver esta misma app en un instalador `.exe` |

## Modelo de datos (SQLite)

```sql
productos(id, sku, nombre, categoria, unidad, costo, precio_venta,
          stock_actual, stock_minimo, activo)
ventas(id, producto_id → productos, fecha, cantidad, precio_unitario, importe)
proveedores(id, nombre, lead_time_dias)
importaciones(id, fecha, archivo, filas_ok, filas_error, estado, detalle)
alertas(id, tipo, severidad, producto_id, mensaje, fecha, leida)
```

## Cómo funciona el asistente (IA local)

1. El usuario escribe una pregunta en español ("¿qué debo comprar esta semana?").
2. El backend construye un **contexto** con cifras del negocio (KPIs, alertas, top productos).
3. Se envía contexto + pregunta a Ollama (`POST /api/chat` de Ollama, sin internet).
4. El LLM responde citando cifras. Si no tiene el dato, lo dice.

**Semana 3 — Function calling:** el LLM podrá invocar herramientas expuestas por la API:

| Herramienta | Endpoint asociado |
|---|---|
| `obtener_kpis` | `GET /api/kpis` |
| `predecir_demanda(producto, dias)` | `GET /api/predicciones/{producto_id}` |
| `productos_baja_rotacion()` | `GET /api/analisis/rotacion` |
| `riesgo_agotamiento()` | `GET /api/recomendaciones/compra` |

## Fórmulas del motor estadístico (implementa Persona A, semana 2)

- **Rotación** = unidades vendidas (90 días) / stock promedio
- **Días de cobertura** = stock actual / venta diaria promedio
- **Punto de reorden** = venta diaria promedio × lead time del proveedor + stock de seguridad
- **Predicción de demanda**: media móvil → suavizado exponencial (Holt) → ARIMA si hace falta (`statsforecast`)
- **Anomalías**: z-score de ventas semanales; alerta si |z| > 3
