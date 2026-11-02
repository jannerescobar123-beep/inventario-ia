import { useRef, useState } from 'react'
import { enviarPregunta } from '../api.js'

const PREGUNTAS_SUGERIDAS = [
  '¿Qué debo comprar esta semana?',
  '¿Qué productos están vendiendo menos?',
  '¿Cuáles pueden agotarse pronto?',
  '¿Qué productos tienen una rotación muy baja?',
]

export default function Chat() {
  const [mensajes, setMensajes] = useState([])
  const [texto, setTexto] = useState('')
  const [pensando, setPensando] = useState(false)
  const finChat = useRef(null)

  function desplazarAbajo() {
    requestAnimationFrame(() => finChat.current?.scrollIntoView({ behavior: 'smooth' }))
  }

  async function preguntar(pregunta) {
    const preguntaLimpia = (pregunta ?? texto).trim()
    if (!preguntaLimpia || pensando) return

    setMensajes((m) => [...m, { rol: 'usuario', contenido: preguntaLimpia }])
    setTexto('')
    setPensando(true)
    desplazarAbajo()

    try {
      const { data } = await enviarPregunta(preguntaLimpia)
      setMensajes((m) => [...m, { rol: 'ia', contenido: data.respuesta, conectado: data.conectado }])
    } catch {
      setMensajes((m) => [
        ...m,
        { rol: 'ia', contenido: '⚠️ Error de conexión con el backend (:8000).', conectado: false },
      ])
    } finally {
      setPensando(false)
      desplazarAbajo()
    }
  }

  return (
    <div className="chat">
      <div className="chat-mensajes">
        {mensajes.length === 0 && (
          <div className="aviso">
            Pregúntale lo que quieras sobre tu negocio. La IA corre en tu propio PC (Ollama).
          </div>
        )}
        {mensajes.map((m, i) => (
          <div key={i} className={`mensaje ${m.rol}`}>
            {m.contenido}
            {m.rol === 'ia' && m.conectado === false && <span className="etiqueta-offline">sin conexión IA</span>}
          </div>
        ))}
        {pensando && <div className="mensaje ia pensando">Pensando…</div>}
        <div ref={finChat} />
      </div>

      <div className="chat-sugerencias">
        {PREGUNTAS_SUGERIDAS.map((p) => (
          <button key={p} className="boton-sugerencia" onClick={() => preguntar(p)} disabled={pensando}>
            {p}
          </button>
        ))}
      </div>

      <form
        className="chat-entrada"
        onSubmit={(e) => {
          e.preventDefault()
          preguntar()
        }}
      >
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Escribe tu pregunta… (ej. ¿qué compro esta semana?)"
          disabled={pensando}
        />
        <button type="submit" disabled={pensando || !texto.trim()}>
          Enviar
        </button>
      </form>
    </div>
  )
}
