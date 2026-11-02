import { useEffect, useState } from 'react'
import { getAlertas, getKpis } from '../api.js'

const formatoMoneda = (valor) =>
  new Intl.NumberFormat('es', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(valor || 0)

export default function Dashboard() {
  const [kpis, setKpis] = useState(null)
  const [alertas, setAlertas] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([getKpis(), getAlertas()])
      .then(([rKpis, rAlertas]) => {
        setKpis(rKpis.data)
        setAlertas(rAlertas.data)
      })
      .catch(() => setError('No se pudo conectar con el backend. ¿Está corriendo en :8000?'))
  }, [])

  if (error) return <div className="aviso error">{error}</div>
  if (!kpis) return <div className="aviso">Cargando datos del negocio…</div>

  const sinDatos = kpis.num_ventas === 0

  return (
    <div>
      {sinDatos && (
        <div className="aviso">
          Aún no hay ventas cargadas. Ve a <strong>📥 Importar</strong> y sube un archivo Excel
          (o genera datos de prueba con <code>python scripts/generar_datos_prueba.py</code>).
        </div>
      )}

      <section className="tarjetas">
        <div className="tarjeta"><span className="tarjeta-valor">{formatoMoneda(kpis.ventas_totales)}</span><span className="tarjeta-nombre">Ventas totales</span></div>
        <div className="tarjeta"><span className="tarjeta-valor">{kpis.num_ventas.toLocaleString('es')}</span><span className="tarjeta-nombre">N° de ventas</span></div>
        <div className="tarjeta"><span className="tarjeta-valor">{formatoMoneda(kpis.ticket_promedio)}</span><span className="tarjeta-nombre">Ticket promedio</span></div>
        <div className="tarjeta"><span className="tarjeta-valor">{Math.round(kpis.unidades_vendidas).toLocaleString('es')}</span><span className="tarjeta-nombre">Unidades vendidas</span></div>
        <div className="tarjeta"><span className="tarjeta-valor">{kpis.num_productos}</span><span className="tarjeta-nombre">Productos</span></div>
        <div className="tarjeta">
          <span className="tarjeta-valor tarjeta-fecha">
            {kpis.periodo_inicio ? `${kpis.periodo_inicio} → ${kpis.periodo_fin}` : '—'}
          </span>
          <span className="tarjeta-nombre">Período analizado</span>
        </div>
      </section>

      <h2>🔔 Alertas recientes</h2>
      {alertas.length === 0 ? (
        <p className="texto-secundario">Sin alertas por ahora. TODO(Persona A): generador de alertas (semana 2).</p>
      ) : (
        <ul className="lista-alertas">
          {alertas.map((a) => (
            <li key={a.id} className={`alerta severidad-${a.severidad}`}>
              <strong>{a.tipo}</strong> — {a.mensaje}
            </li>
          ))}
        </ul>
      )}

      {/* TODO(Persona B): gráfico de ventas por día con Recharts (ya está en package.json) */}
    </div>
  )
}
