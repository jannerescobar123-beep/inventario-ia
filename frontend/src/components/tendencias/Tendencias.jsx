import { useCallback, useEffect, useState } from "react"
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import api from "../../utils/api"

const COLOR_GRID = "rgba(255,255,255,.08)"
const COLOR_EJE = "#94A3B8"

const GRANULARIDADES = [
  { valor: "dia", etiqueta: "Día" },
  { valor: "semana", etiqueta: "Semana" },
  { valor: "mes", etiqueta: "Mes" },
]

function moneda(valor) {
  // Dos decimales siempre: una columna de importes con «$5.435» y «$5.553,6»
  // alineados en vertical se lee mal y parece un error de cálculo.
  return `$${Number(valor ?? 0).toLocaleString("es-CO", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function numero(valor) {
  return Number(valor ?? 0).toLocaleString("es-CO")
}

/** +12,5 % / −8,1 %. El signo menos tipográfico no engaña a nadie. */
function porcentaje(valor) {
  if (valor === null || valor === undefined) return "—"
  const signo = valor > 0 ? "+" : ""
  return `${signo}${valor.toLocaleString("es-CO", { maximumFractionDigits: 1 })} %`
}

function claseDelta(valor) {
  if (valor === null || valor === undefined || valor === 0) return "delta-flat"
  return valor > 0 ? "delta-up" : "delta-down"
}

const TITULOS = {
  semana: "Semana actual vs. la anterior",
  mes: "Mes actual vs. el anterior",
  mes_anio: "Mes actual vs. el mismo mes del año pasado",
}

function TarjetaComparacion({ datos, clave }) {
  if (!datos) {
    return (
      <article className="kpi-card">
        <span className="kpi-label">{TITULOS[clave]}</span>
        <div className="kpi-value kpi-value-muted">—</div>
        <span className="kpi-hint">Cargando…</span>
      </article>
    )
  }

  if (!datos.disponible) {
    return (
      <article className="kpi-card kpi-card-muted">
        <span className="kpi-label">{TITULOS[clave]}</span>
        <div className="kpi-value kpi-value-muted">Sin comparación</div>
        <span className="kpi-hint">{datos.motivo}</span>
      </article>
    )
  }

  const { actual, referencia, variacion } = datos

  return (
    <article className="kpi-card">
      <span className="kpi-label">{TITULOS[clave]}</span>
      <div className={`kpi-value delta ${claseDelta(variacion.unidades_pct)}`}>
        {porcentaje(variacion.unidades_pct)}
      </div>
      <span className="kpi-hint">
        {numero(actual.unidades)} unidades ahora · {numero(referencia.unidades)} en{" "}
        {referencia.etiqueta}
      </span>
      <span className={`kpi-hint delta ${claseDelta(variacion.ingresos_pct)}`}>
        Ingresos {porcentaje(variacion.ingresos_pct)} ({moneda(actual.ingresos)} vs.{" "}
        {moneda(referencia.ingresos)})
      </span>
      {datos.completo === false && (
        <span className="kpi-nota">
          Periodo en curso: {datos.dias_con_datos} de {datos.dias_totales_periodo} días. No está
          ajustado por días.
        </span>
      )}
    </article>
  )
}

const Tendencias = () => {
  const [granularidad, setGranularidad] = useState("semana")
  const [serie, setSerie] = useState(null)
  const [comparaciones, setComparaciones] = useState(null)
  const [error, setError] = useState("")
  const [cargandoSerie, setCargandoSerie] = useState(true)

  const cargarSerie = useCallback(async () => {
    setCargandoSerie(true)
    setError("")
    try {
      const datos = await api.tendencias(granularidad)
      setSerie(datos)
    } catch (e) {
      setError(`No se pudo conectar con la API: ${e.message}`)
    } finally {
      setCargandoSerie(false)
    }
  }, [granularidad])

  const cargarComparaciones = useCallback(async () => {
    try {
      const [semana, mes, mesAnio] = await Promise.all([
        api.comparacion("semana", "anterior"),
        api.comparacion("mes", "anterior"),
        api.comparacion("mes", "anio_anterior"),
      ])
      setComparaciones({ semana, mes, mes_anio: mesAnio })
    } catch (e) {
      setError(`No se pudo conectar con la API: ${e.message}`)
    }
  }, [])

  useEffect(() => {
    cargarSerie()
  }, [cargarSerie])

  useEffect(() => {
    cargarComparaciones()
  }, [cargarComparaciones])

  const puntos = serie?.puntos ?? []
  const resumen = serie?.resumen
  const hayDatos = puntos.some((p) => p.unidades > 0)
  // Nombre visible («Día»/«Semana»/«Mes»), no el slug interno: el lector de
  // pantalla no debe leer «por dia» sin tilde.
  const nombreGranularidad =
    GRANULARIDADES.find((opcion) => opcion.valor === granularidad)?.etiqueta ??
    granularidad

  const recargar = () => {
    cargarSerie()
    cargarComparaciones()
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Cómo van las ventas</h1>
        <p className="page-subtitle">
          Serie calculada sobre tus ventas importadas y comparada con el periodo anterior. Todo
          ocurre en este equipo.
          {serie?.ancla && ` Los datos llegan hasta el ${serie.ancla}.`}
        </p>
      </div>

      {error && (
        <div className="error-state">
          <strong>Backend no disponible</strong>
          <span>{error}</span>
          <button type="button" className="btn btn-primary" onClick={recargar}>
            Reintentar
          </button>
        </div>
      )}

      <div className="kpi-grid kpi-grid-tres">
        <TarjetaComparacion datos={comparaciones?.semana} clave="semana" />
        <TarjetaComparacion datos={comparaciones?.mes} clave="mes" />
        <TarjetaComparacion datos={comparaciones?.mes_anio} clave="mes_anio" />
      </div>

      <div className="section-head">
        <h2 className="section-title">Evolución de las ventas</h2>
        <div className="acciones-orden">
          <span className="count-chip">{numero(resumen?.unidades_totales)} unidades</span>
          <label className="form-label visually-hidden" htmlFor="granularidad">
            Agrupar por
          </label>
          <select
            id="granularidad"
            className="form-select form-select-inline"
            value={granularidad}
            onChange={(evento) => setGranularidad(evento.target.value)}
          >
            {GRANULARIDADES.map((opcion) => (
              <option key={opcion.valor} value={opcion.valor}>
                Por {opcion.etiqueta.toLowerCase()}
              </option>
            ))}
          </select>
        </div>
      </div>

      <section className="surface-card">
        {cargandoSerie ? (
          <div className="loading-state">
            <span className="spinner" aria-hidden="true" />
            <span>Calculando la serie…</span>
          </div>
        ) : !hayDatos ? (
          <div className="empty-state">
            <p className="mb-0">No hay ventas registradas en este periodo.</p>
            <p className="state-hint">Importa un archivo desde la sección «Importar».</p>
          </div>
        ) : (
          <div
            className="chart-box chart-box-alto"
            role="img"
            aria-label={`Evolución de unidades vendidas por ${nombreGranularidad.toLowerCase()}. La tabla inferior tiene los mismos datos en texto.`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={puntos} margin={{ top: 12, right: 32, bottom: 8, left: 0 }}>
                <CartesianGrid stroke={COLOR_GRID} vertical={false} />
                <XAxis
                  dataKey="etiqueta"
                  stroke={COLOR_EJE}
                  tick={{ fill: COLOR_EJE, fontSize: 12 }}
                  interval="preserveStartEnd"
                  minTickGap={18}
                />
                <YAxis
                  stroke={COLOR_EJE}
                  tick={{ fill: COLOR_EJE, fontSize: 12 }}
                  allowDecimals={false}
                  width={44}
                />
                <Tooltip
                  cursor={{ stroke: "rgba(99,102,241,.4)" }}
                  contentStyle={{
                    background: "#151A21",
                    border: "1px solid rgba(255,255,255,.08)",
                    borderRadius: 12,
                    color: "#F1F5F9",
                  }}
                  labelStyle={{ color: "#F1F5F9" }}
                  itemStyle={{ color: "#E0E7FF" }}
                  formatter={(valor) => [numero(valor), "Unidades"]}
                />
                <Line
                  type="monotone"
                  dataKey="unidades"
                  stroke="#6366F1"
                  strokeWidth={2.5}
                  dot={{ r: 2.5, fill: "#6366F1" }}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {resumen && (
        <p className="state-hint resumen-tendencia">
          {resumen.periodos} periodo(s) · {numero(resumen.unidades_totales)} unidades ·{" "}
          {moneda(resumen.ingresos_totales)} · tendencia de la serie{" "}
          <strong className={`delta ${resumen.direccion === "sube"
            ? "delta-up"
            : resumen.direccion === "baja"
              ? "delta-down"
              : "delta-flat"}`}>
            {resumen.direccion === "sube"
              ? "al alza"
              : resumen.direccion === "baja"
                ? "a la baja"
                : "estable"}
          </strong>
          {resumen.direccion !== "estable" &&
            ` (${porcentaje(resumen.pendiente_relativa_pct)} por periodo)`}
        </p>
      )}

      <div className="section-head">
        <h2 className="section-title">Detalle por periodo</h2>
        <span className="count-chip">{puntos.length} periodo(s)</span>
      </div>

      {puntos.length === 0 ? (
        // Fuera de la tabla a propósito: dentro de un <td> con colspan dentro de
        // una tabla de 640 px, en un móvil de 360 px el texto se recorta.
        <div className="empty-state">
          <p className="mb-0">Sin datos para mostrar.</p>
          <p className="state-hint">
            Importa un archivo desde la sección «Importar» o cambia la granularidad.
          </p>
        </div>
      ) : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Detalle por periodo">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Periodo</th>
                <th scope="col" className="num">Unidades</th>
                <th scope="col" className="num">Ingresos</th>
                <th scope="col" className="num">Ventas</th>
                <th scope="col" className="num">Precio medio</th>
                <th scope="col" className="num">Variación</th>
              </tr>
            </thead>
            <tbody>
              {[...puntos].reverse().map((punto) => (
                <tr key={punto.periodo}>
                  <td>{punto.etiqueta}</td>
                  <td className="num">{numero(punto.unidades)}</td>
                  <td className="num">{moneda(punto.ingresos)}</td>
                  <td className="num">{numero(punto.num_ventas)}</td>
                  <td className="num">
                    {punto.precio_medio_unidad === null ? "—" : moneda(punto.precio_medio_unidad)}
                  </td>
                  <td className={`num delta ${claseDelta(punto.variacion_unidades_pct)}`}>
                    {porcentaje(punto.variacion_unidades_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

export default Tendencias
