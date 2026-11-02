import { useEffect, useMemo, useState } from 'react'
import { getProductos } from '../api.js'

const formatoMoneda = (valor) =>
  valor > 0
    ? new Intl.NumberFormat('es', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(valor)
    : '—'

const formatoMargen = (costo, precio) => {
  if (!costo || !precio) return '—'
  const margen = ((precio - costo) / precio) * 100
  return `${margen.toFixed(1)}%`
}

function EstadoStock({ producto }) {
  if (!producto.stock_minimo) {
    return <span className="badge neutral">Sin mínimo definido</span>
  }
  return producto.stock_actual <= producto.stock_minimo
    ? <span className="badge peligro">⚠ Bajo stock</span>
    : <span className="badge ok">OK</span>
}

export default function Productos() {
  const [productos, setProductos] = useState(null)
  const [error, setError] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [categoria, setCategoria] = useState('')
  const [soloBajoStock, setSoloBajoStock] = useState(false)

  useEffect(() => {
    getProductos()
      .then((r) => setProductos(r.data))
      .catch(() => setError('No se pudo conectar con el backend (:8000).'))
  }, [])

  const categorias = useMemo(
    () => [...new Set((productos ?? []).map((p) => p.categoria))].sort(),
    [productos],
  )

  const filtrados = useMemo(() => {
    let lista = productos ?? []
    const texto = busqueda.trim().toLowerCase()
    if (texto) {
      lista = lista.filter(
        (p) => p.nombre.toLowerCase().includes(texto) || (p.sku ?? '').toLowerCase().includes(texto),
      )
    }
    if (categoria) lista = lista.filter((p) => p.categoria === categoria)
    if (soloBajoStock) lista = lista.filter((p) => p.stock_minimo > 0 && p.stock_actual <= p.stock_minimo)
    return lista
  }, [productos, busqueda, categoria, soloBajoStock])

  if (error) return <div className="aviso error">{error}</div>
  if (!productos) return <div className="aviso">Cargando catálogo…</div>

  if (productos.length === 0) {
    return (
      <div className="aviso">
        Aún no hay productos. Importa tus ventas en <strong>📥 Importar</strong> — los productos
        se crean automáticamente desde el archivo.
        <br />
        <small className="texto-secundario">
          TODO(Persona A): importar también la hoja "productos" (stock, costo, mínimo) — semana 1.
        </small>
      </div>
    )
  }

  return (
    <div>
      <section className="filtros">
        <input
          className="buscador"
          type="search"
          placeholder="🔍 Buscar por nombre o SKU…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <select value={categoria} onChange={(e) => setCategoria(e.target.value)}>
          <option value="">Todas las categorías ({categorias.length})</option>
          {categorias.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <label className="casilla">
          <input
            type="checkbox"
            checked={soloBajoStock}
            onChange={(e) => setSoloBajoStock(e.target.checked)}
          />
          Solo bajo stock
        </label>
      </section>

      <p className="texto-secundario resumen-tabla">
        Mostrando <strong>{filtrados.length}</strong> de {productos.length} productos
        {categoria && <> en <strong>{categoria}</strong></>}
      </p>

      <div className="tabla-contenedor">
        <table className="tabla">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Producto</th>
              <th>Categoría</th>
              <th className="num">Precio</th>
              <th className="num">Costo</th>
              <th className="num">Margen</th>
              <th className="num">Stock</th>
              <th className="num">Mínimo</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {filtrados.map((p) => (
              <tr key={p.id}>
                <td className="texto-suave">{p.sku ?? '—'}</td>
                <td className="celda-nombre">{p.nombre}</td>
                <td>{p.categoria}</td>
                <td className="num">{formatoMoneda(p.precio_venta)}</td>
                <td className="num">{formatoMoneda(p.costo)}</td>
                <td className="num">{formatoMargen(p.costo, p.precio_venta)}</td>
                <td className="num">{Math.round(p.stock_actual)}</td>
                <td className="num texto-suave">{Math.round(p.stock_minimo)}</td>
                <td><EstadoStock producto={p} /></td>
              </tr>
            ))}
            {filtrados.length === 0 && (
              <tr>
                <td colSpan={9} className="texto-suave celda-vacia">
                  Ningún producto coincide con los filtros.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
