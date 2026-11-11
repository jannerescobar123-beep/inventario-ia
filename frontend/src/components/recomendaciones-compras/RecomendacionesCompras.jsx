import { useCallback, useEffect, useState } from "react"
import api from "../../utils/api"

function normalizar(texto) {
  return String(texto ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
}

function claseUrgencia(urgencia) {
  const texto = normalizar(urgencia)
  if (texto.startsWith("crit")) return "urg-critico"
  if (texto.startsWith("alt")) return "urg-alto"
  if (texto.startsWith("med")) return "urg-medio"
  return "urg-bajo"
}

const RecomendacionesCompras = () => {
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState("")
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    setError("")
    try {
      const respuesta = await api.recomendaciones()
      setDatos(respuesta)
    } catch (e) {
      setError(`No se pudo conectar con la API: ${e.message}`)
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  if (cargando) {
    return (
      <div className="loading-state">
        <span className="spinner" aria-hidden="true" />
        <span>Calculando qué comprar…</span>
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

  const recomendaciones = datos?.recomendaciones ?? []
  const criticas = recomendaciones.filter((r) => claseUrgencia(r.urgencia) === "urg-critico").length
  const totalUnidades = recomendaciones.reduce((suma, r) => suma + (r.cantidad_sugerida ?? 0), 0)

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Qué comprar esta semana</h1>
        <p className="page-subtitle">
          Lista calculada con tu stock real, la demanda de los últimos 7 días y el tiempo de entrega
          del proveedor ({datos?.lead_time_asumido ?? 7} días).
        </p>
      </div>

      <div className="kpi-grid">
        <article className="kpi-card is-hero">
          <span className="kpi-label">Unidades sugeridas</span>
          <div className="kpi-value">{totalUnidades.toLocaleString("es-CO")}</div>
          <span className="kpi-hint">Total de la lista de compra</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Productos a comprar</span>
          <div className="kpi-value">{recomendaciones.length}</div>
          <span className="kpi-hint">Con stock por debajo del punto de reorden</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Urgencia crítica</span>
          <div className="kpi-value">{criticas}</div>
          <span className="kpi-hint">Se agotan antes de recibir el pedido</span>
        </article>
      </div>

      <div className="section-head">
        <h2 className="section-title">Lista de compra sugerida</h2>
        <span className="count-chip">{recomendaciones.length} producto(s)</span>
      </div>

      {recomendaciones.length === 0 ? (
        <div className="empty-state">
          <p className="mb-0">No hace falta comprar nada.</p>
          <p className="state-hint">Tu stock cubre la demanda proyectada.</p>
        </div>
      ) : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Lista de compra sugerida">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Producto</th>
                <th scope="col" className="num">Stock</th>
                <th scope="col" className="num">Mínimo</th>
                <th scope="col" className="num">Demanda 7 d</th>
                <th scope="col" className="num">Punto de reorden</th>
                <th scope="col" className="num">Comprar</th>
                <th scope="col">Urgencia</th>
                <th scope="col">Fecha sugerida</th>
                <th scope="col">Llegada estimada</th>
              </tr>
            </thead>
            <tbody>
              {recomendaciones.map((recomendacion) => (
                <tr key={recomendacion.producto_id}>
                  <td>{recomendacion.producto}</td>
                  <td className="num">{recomendacion.stock_actual}</td>
                  <td className="num">{recomendacion.stock_minimo}</td>
                  <td className="num">{recomendacion.demanda_proyectada}</td>
                  <td className="num">{recomendacion.punto_reorden}</td>
                  <td className="num">
                    <strong>{recomendacion.cantidad_sugerida}</strong>
                  </td>
                  <td>
                    <span className={`urgency-chip ${claseUrgencia(recomendacion.urgencia)}`}>
                      {recomendacion.urgencia}
                    </span>
                  </td>
                  <td>{recomendacion.fecha_sugerida}</td>
                  <td>{recomendacion.fecha_entrega_estimada}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="state-hint">
        Calculado sobre {datos?.total_analizados ?? 0} producto(s) con stock bajo. Última venta
        registrada: {datos?.fecha_referencia_demanda ?? "—"} (base de la demanda de 7 días).
      </p>
    </>
  )
}

export default RecomendacionesCompras
