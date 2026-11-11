import { useCallback, useEffect, useState } from "react"
import api from "../../utils/api"

function nivelRiesgo(dias) {
  if (dias === null || dias === undefined) return { clase: "urg-bajo", texto: "sin ventas" }
  if (dias <= 3) return { clase: "urg-critico", texto: `${dias} días` }
  if (dias <= 7) return { clase: "urg-alto", texto: `${dias} días` }
  if (dias <= 14) return { clase: "urg-medio", texto: `${dias} días` }
  return { clase: "urg-bajo", texto: `${dias} días` }
}

function moneda(valor) {
  return `$${Number(valor ?? 0).toLocaleString("es-CO")}`
}

const PanelAlertas = () => {
  const [alertas, setAlertas] = useState([])
  const [analisis, setAnalisis] = useState(null)
  const [error, setError] = useState("")
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    try {
      const datos = await api.alertas()
      setAlertas(datos.riesgo_agotamiento ?? [])
      setAnalisis(datos.comportamiento ?? null)
      setError("")
    } catch (e) {
      setError(`No se pudo conectar con la API: ${e.message}`)
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    cargar()
    // Regeneración automática cada 5 minutos (RF-31)
    const intervalo = window.setInterval(cargar, 5 * 60 * 1000)
    return () => window.clearInterval(intervalo)
  }, [cargar])

  if (cargando) {
    return (
      <div className="loading-state">
        <span className="spinner" aria-hidden="true" />
        <span>Calculando alertas…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="error-state">
        <strong>Backend no disponible</strong>
        <span>{error}</span>
        <span className="state-hint">Comprueba que la API responde en el puerto 8000.</span>
        <button type="button" className="btn btn-primary" onClick={cargar}>
          Reintentar
        </button>
      </div>
    )
  }

  const criticos = alertas.filter((a) => a.dias_estimados !== null && a.dias_estimados <= 3).length

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Alertas inteligentes</h1>
        <p className="page-subtitle">
          Productos que se agotan si no repones, calculados con tu stock y el ritmo real de ventas.
        </p>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">En riesgo</span>
          <div className="stat-value num">{alertas.length}</div>
        </div>
        <div className="stat-card">
          <span className="stat-label">Críticos (≤ 3 días)</span>
          <div className="stat-value num">{criticos}</div>
        </div>
        <div className="stat-card">
          <span className="stat-label">Picos detectados</span>
          <div className="stat-value num">{analisis?.picos_detectados ?? 0}</div>
        </div>
        <div className="stat-card">
          <span className="stat-label">Caídas detectadas</span>
          <div className="stat-value num">{analisis?.caidas_detectadas ?? 0}</div>
        </div>
      </div>

      <div className="section-head">
        <h2 className="section-title">Riesgo de agotamiento</h2>
        <span className={`urgency-chip ${alertas.length > 0 ? "urg-alto" : "urg-bajo"}`}>
          {alertas.length} producto(s)
        </span>
      </div>

      {alertas.length === 0 ? (
        <div className="empty-state">
          <p className="mb-0">No hay productos en riesgo.</p>
          <p className="state-hint">Tu stock cubre el ritmo de venta actual.</p>
        </div>
      ) : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Productos en riesgo de agotamiento">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Producto</th>
                <th scope="col" className="num">Stock actual</th>
                <th scope="col" className="num">Stock mínimo</th>
                <th scope="col" className="num">Días estimados</th>
                <th scope="col" className="num">Valor en inventario</th>
              </tr>
            </thead>
            <tbody>
              {alertas.map((alerta) => {
                const riesgo = nivelRiesgo(alerta.dias_estimados)
                const critica = alerta.dias_estimados !== null && alerta.dias_estimados <= 7
                return (
                  <tr key={alerta.producto_id} className={critica ? "row-critical" : undefined}>
                    <td>{alerta.producto}</td>
                    <td className="num">{alerta.stock_actual}</td>
                    <td className="num">{alerta.stock_minimo}</td>
                    <td className="num">
                      <span className={`urgency-chip ${riesgo.clase}`}>{riesgo.texto}</span>
                    </td>
                    <td className="num">{moneda(alerta.valor_inventario)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="section-head">
        <h2 className="section-title">Comportamiento de ventas</h2>
        <span className={`urgency-chip ${analisis?.alerta ? "urg-medio" : "urg-bajo"}`}>
          {analisis?.alerta ? "Anomalías detectadas" : "Comportamiento normal"}
        </span>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Media diaria</span>
          <div className="stat-value num">{analisis?.media_diaria ?? 0} u.</div>
        </div>
        <div className="stat-card">
          <span className="stat-label">Desviación</span>
          <div className="stat-value num">{analisis?.desviacion_std ?? 0}</div>
        </div>
        <div className="stat-card">
          <span className="stat-label">Última actualización</span>
          <div className="stat-value">
            {analisis?.ultima_actualizacion
              ? new Date(analisis.ultima_actualizacion).toLocaleTimeString()
              : "—"}
          </div>
        </div>
      </div>
    </>
  )
}

export default PanelAlertas
