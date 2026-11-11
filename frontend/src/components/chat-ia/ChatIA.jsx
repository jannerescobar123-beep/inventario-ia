import { useEffect, useRef, useState } from "react"
import api from "../../utils/api"

const PREGUNTAS_FRECUENTES = [
  "¿Qué debo comprar esta semana?",
  "¿Qué productos tienen baja rotación?",
  "¿Cuáles son mis KPIs principales?",
  "¿Algún producto se agota pronto?",
]

function hora(fechaIso) {
  try {
    return new Date(fechaIso).toLocaleTimeString()
  } catch {
    return ""
  }
}

function IconoEnviar() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 19V5M6 11l6-6 6 6" />
    </svg>
  )
}

function IconoCerrar() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}

const ChatIA = ({ variante = "pagina", onCerrar }) => {
  const [mensaje, setMensaje] = useState("")
  const [historial, setHistorial] = useState([])
  const [esperando, setEsperando] = useState(false)
  const [error, setError] = useState("")
  const [ultimoContexto, setUltimoContexto] = useState(null)

  const finRef = useRef(null)
  const enPagina = variante === "pagina"

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [historial, esperando])

  const enviar = async (event) => {
    event.preventDefault()
    const texto = mensaje.trim()
    if (!texto || esperando) return

    const mensajeUsuario = { rol: "usuario", contenido: texto, fecha: new Date().toISOString() }
    setHistorial((actual) => [...actual, mensajeUsuario])
    setMensaje("")
    setEsperando(true)
    setError("")

    try {
      const datos = await api.chat(texto, historial)
      setHistorial((actual) => [
        ...actual,
        {
          rol: "asistente",
          contenido: datos.respuesta,
          herramientas: datos.herramientas,
          modelo: datos.modelo,
          fecha: new Date().toISOString(),
        },
      ])
      setUltimoContexto(datos.contexto)
    } catch (e) {
      setError(e.message)
    } finally {
      setEsperando(false)
    }
  }

  const limpiar = () => {
    setHistorial([])
    setUltimoContexto(null)
    setError("")
  }

  return (
    <div className={`chat-inner${enPagina ? " is-page" : ""}`}>
      <div className="chat-head">
        <span>Asistente IA</span>
        <span className={`api-badge ${esperando ? "is-off" : "is-on"}`}>
          {esperando ? "Pensando…" : "En línea"}
        </span>
        <span className="chat-head-spacer" />
        {!enPagina && (
          <button type="button" className="icon-btn" aria-label="Cerrar asistente" onClick={onCerrar}>
            <IconoCerrar />
          </button>
        )}
        {enPagina && (
          <button type="button" className="btn btn-ghost" onClick={limpiar} disabled={historial.length === 0}>
            Limpiar
          </button>
        )}
      </div>

      <div className="chat-body">
        <div className="chat-messages" aria-live="polite">
          {historial.length === 0 && (
            <div className="empty-state">
              <p className="mb-2">Pregunta por tus ventas, tu stock o qué comprar esta semana.</p>
              <p className="state-hint">IA local (Ollama): nada sale de este equipo.</p>
            </div>
          )}

          {historial.map((item, indice) => (
            <div
              key={`${item.fecha}-${indice}`}
              className={`chat-msg ${item.rol === "usuario" ? "is-user" : "is-bot"}`}
            >
              <div className="msg-text">{item.contenido}</div>
              {item.herramientas?.length > 0 && (
                <span className="msg-meta">datos: {item.herramientas.join(", ")}</span>
              )}
              <span className="msg-meta">
                {hora(item.fecha)}
                {item.modelo ? ` · ${item.modelo}` : ""}
              </span>
            </div>
          ))}

          {esperando && (
            <div className="loading-state">
              <span className="spinner" aria-hidden="true" />
              <span>Consultando los datos del negocio y redactando la respuesta…</span>
            </div>
          )}

          {error && (
            <div className="error-state">
              <strong>No se pudo obtener la respuesta</strong>
              <span>{error}</span>
              <span className="state-hint">Verifica que el backend esté corriendo en el puerto 8000.</span>
            </div>
          )}

          <div ref={finRef} />
        </div>

        <div className="chat-tools">
          {PREGUNTAS_FRECUENTES.map((pregunta) => (
            <button
              key={pregunta}
              type="button"
              onClick={() => setMensaje(pregunta)}
              disabled={esperando}
            >
              {pregunta}
            </button>
          ))}
        </div>

        <form className="chat-input-row" onSubmit={enviar}>
          <input
            id={enPagina ? "chat-mensaje-pagina" : "chat-mensaje"}
            name="mensaje"
            className="chat-input"
            type="text"
            value={mensaje}
            onChange={(event) => setMensaje(event.target.value)}
            placeholder="Escribe tu pregunta…"
            aria-label="Mensaje para el asistente"
            disabled={esperando}
          />
          <button
            type="submit"
            className="chat-send-btn"
            aria-label="Enviar mensaje"
            disabled={esperando || !mensaje.trim()}
          >
            <IconoEnviar />
          </button>
        </form>
      </div>

      {enPagina && ultimoContexto && (
        <div className="surface-card chat-context">
          <div className="card-head">
            <h2 className="card-title">Cifras consultadas en la última respuesta</h2>
          </div>
          <details>
            <summary className="state-hint">Ver datos crudos de SQLite</summary>
            <pre>{JSON.stringify(ultimoContexto, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  )
}

export default ChatIA
