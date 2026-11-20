import { useCallback, useEffect, useState } from "react"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import api from "../../utils/api"

function moneda(valor) {
  return `$${Number(valor ?? 0).toLocaleString("es-CO")}`
}

const COLOR_GRID = "rgba(255,255,255,.08)"
const COLOR_EJE = "#94A3B8"

// RF-43: opciones del selector. Si el producto tiene un proveedor dado de baja,
// se añade arriba para que el selector muestre la verdad en vez de un valor que
// no existe entre las opciones (que dejaría el <select> en blanco).
function opcionesDeProveedor(producto, proveedores) {
  const opciones = proveedores.map((proveedor) => ({ id: proveedor.id, nombre: proveedor.nombre }))
  if (producto.proveedor_id && !opciones.some((opcion) => opcion.id === producto.proveedor_id)) {
    opciones.unshift({
      id: producto.proveedor_id,
      nombre: `${producto.proveedor ?? "Proveedor"} (de baja)`,
    })
  }
  return opciones
}

const Dashboard = () => {
  const [kpis, setKpis] = useState(null)
  const [productos, setProductos] = useState([])
  const [proveedores, setProveedores] = useState([])
  const [error, setError] = useState("")
  const [cargando, setCargando] = useState(true)
  const [guardandoProveedor, setGuardandoProveedor] = useState(null)
  const [avisoProveedor, setAvisoProveedor] = useState("")

  const cargar = useCallback(async () => {
    setCargando(true)
    setError("")
    try {
      // Si el listado de proveedores falla, el Panel sigue siendo útil: solo se
      // pierde el selector, no las cifras ni el catálogo.
      const [datosKpis, datosProductos, datosProveedores] = await Promise.all([
        api.kpis(),
        api.productos(),
        api.proveedores(true).catch(() => []),
      ])
      setKpis(datosKpis)
      setProductos(datosProductos)
      setProveedores(datosProveedores)
    } catch (e) {
      setError(`No se pudo conectar con la API: ${e.message}`)
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  const cambiarProveedor = async (producto, valor) => {
    const proveedorId = valor === "" ? null : Number(valor)
    setGuardandoProveedor(producto.id)
    setAvisoProveedor("")
    try {
      await api.asignarProveedor(producto.id, proveedorId)
      // Se relee el catálogo para traer el nombre y el lead time resueltos.
      setProductos(await api.productos())
      setAvisoProveedor(
        proveedorId === null
          ? `«${producto.nombre}» queda sin proveedor: usará el plazo de 7 días.`
          : `Proveedor de «${producto.nombre}» actualizado.`
      )
    } catch (e) {
      setAvisoProveedor(`No se pudo asignar el proveedor: ${e.message}`)
    } finally {
      setGuardandoProveedor(null)
    }
  }

  if (cargando) {
    return (
      <div className="loading-state">
        <span className="spinner" aria-hidden="true" />
        <span>Cargando datos del negocio…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="error-state">
        <strong>Backend no disponible</strong>
        <span>{error}</span>
        <span className="state-hint">
          Arranca el servidor con: <code>python -m uvicorn backend.api.main:app --port 8000</code>
        </span>
        <button type="button" className="btn btn-primary" onClick={cargar}>
          Reintentar
        </button>
      </div>
    )
  }

  const topProductos = kpis?.top_productos ?? []
  const ranking = topProductos.slice(0, 6)

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Tu negocio, de un vistazo</h1>
        <p className="page-subtitle">
          Cifras calculadas sobre las ventas que has importado. Todo ocurre en este equipo.
        </p>
      </div>

      <div className="kpi-grid">
        <article className="kpi-card is-hero">
          <span className="kpi-label">Ventas totales</span>
          <div className="kpi-value">{moneda(kpis?.ventas_totales)}</div>
          <span className="kpi-hint">Datos importados</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Ticket promedio</span>
          <div className="kpi-value">{moneda(kpis?.ticket_promedio)}</div>
          <span className="kpi-hint">Por transacción</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Unidades vendidas</span>
          <div className="kpi-value">{(kpis?.unidades_vendidas ?? 0).toLocaleString("es-CO")}</div>
          <span className="kpi-hint">Total vendido</span>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Margen total</span>
          <div className="kpi-value">{moneda(kpis?.margen_total)}</div>
          <span className="kpi-hint">Diferencia entre venta y costo (RF-09)</span>
        </article>
      </div>

      <div className="split-grid">
        <section className="surface-card">
          <div className="card-head">
            <h2 className="card-title">Productos más vendidos</h2>
            <span className="count-chip">{topProductos.length} producto(s)</span>
          </div>
          {topProductos.length === 0 ? (
            <div className="empty-state">
              <p className="mb-0">Sin ventas registradas.</p>
              <p className="state-hint">Importa un archivo desde la sección «Importar».</p>
            </div>
          ) : (
            <div className="chart-box">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topProductos} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                  <CartesianGrid stroke={COLOR_GRID} vertical={false} />
                  <XAxis
                    dataKey="nombre"
                    stroke={COLOR_EJE}
                    tick={{ fill: COLOR_EJE, fontSize: 12 }}
                    interval={0}
                    angle={-18}
                    textAnchor="end"
                    height={58}
                  />
                  <YAxis
                    stroke={COLOR_EJE}
                    tick={{ fill: COLOR_EJE, fontSize: 12 }}
                    allowDecimals={false}
                    width={44}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(99,102,241,.12)" }}
                    contentStyle={{
                      background: "#151A21",
                      border: "1px solid rgba(255,255,255,.08)",
                      borderRadius: 12,
                      color: "#F1F5F9",
                    }}
                    labelStyle={{ color: "#F1F5F9" }}
                    itemStyle={{ color: "#E0E7FF" }}
                  />
                  <Bar dataKey="cantidad" fill="#6366F1" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        <section className="surface-card">
          <div className="card-head">
            <h2 className="card-title">Ranking de ventas</h2>
          </div>
          {ranking.length === 0 ? (
            <div className="empty-state">
              <p className="mb-0">Aún no hay productos con ventas.</p>
            </div>
          ) : (
            <ol className="rank-list">
              {ranking.map((producto, indice) => (
                <li className="rank-item" key={`${producto.nombre}-${indice}`}>
                  <span className="rank-name">
                    {indice + 1}. {producto.nombre}
                  </span>
                  <span className="rank-value num">{producto.cantidad}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <div className="section-head">
        <h2 className="section-title">Catálogo de productos</h2>
        <span className="count-chip">{productos.length} producto(s)</span>
      </div>

      {avisoProveedor && (
        <p className="aviso aviso-ok" role="status" aria-live="polite">
          {avisoProveedor}
        </p>
      )}

      <div className="table-wrap" tabIndex={0} role="region" aria-label="Catálogo de productos">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">SKU</th>
              <th scope="col">Producto</th>
              <th scope="col">Categoría</th>
              <th scope="col">Proveedor</th>
              <th scope="col" className="num">Costo</th>
              <th scope="col" className="num">Precio</th>
              <th scope="col" className="num">Stock</th>
              <th scope="col" className="num">Mínimo</th>
            </tr>
          </thead>
          <tbody>
            {productos.length === 0 ? (
              <tr>
                <td colSpan={8} className="state-hint">
                  No hay productos en el catálogo.
                </td>
              </tr>
            ) : (
              productos.map((producto) => (
                <tr key={producto.id}>
                  <td>{producto.sku}</td>
                  <td>{producto.nombre}</td>
                  <td>{producto.categoria || "—"}</td>
                  <td>
                    {/* El nombre largo se recorta en el ancho de la celda; el
                        `title` deja leerlo completo sin abrir el desplegable. */}
                    <label className="visually-hidden" htmlFor={`proveedor-${producto.id}`}>
                      Proveedor de {producto.nombre}
                    </label>
                    <select
                      id={`proveedor-${producto.id}`}
                      className="form-select form-select-inline select-proveedor"
                      value={producto.proveedor_id ?? ""}
                      onChange={(evento) => cambiarProveedor(producto, evento.target.value)}
                      disabled={guardandoProveedor === producto.id}
                      title={
                        producto.proveedor
                          ? `${producto.proveedor} — ${producto.lead_time_proveedor} días`
                          : "Sin proveedor (7 días)"
                      }
                    >
                      <option value="">Sin proveedor (7 días)</option>
                      {opcionesDeProveedor(producto, proveedores).map((opcion) => (
                        <option key={opcion.id} value={opcion.id}>
                          {opcion.nombre}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="num">{moneda(producto.costo)}</td>
                  <td className="num">{moneda(producto.precio_venta)}</td>
                  <td className="num">{producto.stock_actual}</td>
                  <td className="num">{producto.stock_minimo}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {proveedores.length === 0 && (
        <p className="state-hint">
          No hay proveedores activos. Créalos en la sección «Proveedores» para que el plazo de
          entrega de cada uno entre en el cálculo de la compra.
        </p>
      )}
    </>
  )
}

export default Dashboard
