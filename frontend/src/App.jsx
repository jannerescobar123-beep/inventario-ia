import { useEffect, useRef, useState } from "react"
import { BrowserRouter as Router, NavLink, Route, Routes, useLocation } from "react-router-dom"
import api from "./utils/api"

import Dashboard from "./components/dashboard/Dashboard"
import WizardImport from "./components/wizard-import/WizardImport"
import PanelAlertas from "./components/panel-alertas/PanelAlertas"
import RecomendacionesCompras from "./components/recomendaciones-compras/RecomendacionesCompras"
import ChatIA from "./components/chat-ia/ChatIA"

const NAVEGACION = [
  { ruta: "/", etiqueta: "Panel de control", fin: true },
  { ruta: "/importar", etiqueta: "Importar" },
  { ruta: "/alertas", etiqueta: "Alertas" },
  { ruta: "/compras", etiqueta: "Qué comprar" },
  { ruta: "/chat", etiqueta: "Chat IA" },
]

function IconoMenu() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  )
}

function IconoCerrar() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}

function IconoChat() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.4-.7L3 21l1.8-5.1A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4Z" />
    </svg>
  )
}

function Estructura() {
  const [estado, setEstado] = useState("comprobando")
  const [menuAbierto, setMenuAbierto] = useState(false)
  const [chatAbierto, setChatAbierto] = useState(false)

  const botonMenuRef = useRef(null)
  const botonChatRef = useRef(null)
  const drawerRef = useRef(null)
  const mainRef = useRef(null)
  const ubicacion = useLocation()

  useEffect(() => {
    let vigente = true
    api
      .health()
      .then(() => vigente && setEstado("ok"))
      .catch(() => vigente && setEstado("sin-conexion"))
    return () => {
      vigente = false
    }
  }, [])

  // El menú se cierra al cambiar de ruta
  useEffect(() => {
    setMenuAbierto(false)
  }, [ubicacion.pathname])

  // Al navegar desde el menú, el foco debe salir del drawer antes de que se oculte
  // con aria-hidden: si un descendiente conserva el foco, el navegador bloquea el
  // aria-hidden y los lectores de pantalla se quedan desorientados.
  const salirDelDrawer = () => {
    if (drawerRef.current?.contains(document.activeElement)) {
      mainRef.current?.focus({ preventScroll: true })
    }
  }

  // Menú móvil: Escape, foco inicial y bloqueo del scroll de fondo
  useEffect(() => {
    if (!menuAbierto) return undefined
    const alPulsar = (evento) => {
      if (evento.key === "Escape") {
        setMenuAbierto(false)
        botonMenuRef.current?.focus()
      }
    }
    document.addEventListener("keydown", alPulsar)
    const overflowPrevio = document.body.style.overflow
    document.body.style.overflow = "hidden"
    drawerRef.current?.querySelector("a")?.focus()
    return () => {
      document.removeEventListener("keydown", alPulsar)
      document.body.style.overflow = overflowPrevio
    }
  }, [menuAbierto])

  // Panel de chat: Escape devuelve el foco al botón flotante
  useEffect(() => {
    if (!chatAbierto) return undefined
    const alPulsar = (evento) => {
      if (evento.key === "Escape") {
        setChatAbierto(false)
        botonChatRef.current?.focus()
      }
    }
    document.addEventListener("keydown", alPulsar)
    return () => document.removeEventListener("keydown", alPulsar)
  }, [chatAbierto])

  // Al abrir el panel, el foco pasa al campo de mensaje. El panel está siempre
  // montado (para poder animarlo), así que el efecto del componente no se
  // vuelve a ejecutar al abrirlo.
  useEffect(() => {
    if (!chatAbierto) return undefined
    const temporizador = window.setTimeout(() => {
      document.getElementById("chat-mensaje")?.focus()
    }, 120)
    return () => window.clearTimeout(temporizador)
  }, [chatAbierto])

  const cerrarMenu = () => {
    setMenuAbierto(false)
    botonMenuRef.current?.focus()
  }

  const cerrarChat = () => {
    setChatAbierto(false)
    botonChatRef.current?.focus()
  }

  const claseEnlace = ({ isActive }) => `nav-link${isActive ? " is-active" : ""}`

  return (
    <div className="app-shell">
      <div className="app-bg" aria-hidden="true">
        <div className="bg-layer" />
        <div className="bg-layer" />
        <div className="bg-layer" />
      </div>

      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            <span className="brand-mark" aria-hidden="true">IA</span>
            <span className="brand-text">Inventario-IA</span>
          </NavLink>

          <ul className="nav-links">
            {NAVEGACION.map((item) => (
              <li key={item.ruta}>
                <NavLink to={item.ruta} end={item.fin} className={claseEnlace}>
                  {item.etiqueta}
                </NavLink>
              </li>
            ))}
          </ul>

          <div className="topbar-actions">
            <span className={`api-badge ${estado === "ok" ? "is-on" : "is-off"}`}>
              {estado === "ok" ? "API conectada" : estado === "sin-conexion" ? "API sin conexión" : "Comprobando…"}
            </span>
            <button
              type="button"
              className="hamburger-btn"
              ref={botonMenuRef}
              aria-label={menuAbierto ? "Cerrar menú" : "Abrir menú"}
              aria-expanded={menuAbierto}
              aria-controls="menu-movil"
              onClick={() => setMenuAbierto((valor) => !valor)}
            >
              {menuAbierto ? <IconoCerrar /> : <IconoMenu />}
            </button>
          </div>
        </div>
      </header>

      {menuAbierto && <div className="nav-backdrop" aria-hidden="true" onClick={cerrarMenu} />}

      <nav
        id="menu-movil"
        ref={drawerRef}
        className={`nav-drawer${menuAbierto ? " is-open" : ""}`}
        /* `inert` en lugar de `aria-hidden`: además de sacar el menú del árbol de
           accesibilidad, retira el foco de sus controles, de modo que ocultar el
           menú nunca deja el foco atrapado dentro (ni dispara el aviso
           «Blocked aria-hidden… retained focus»). React 18 no reconoce `inert`
           como booleano: se pasa como cadena vacía. */
        inert={menuAbierto ? undefined : ""}
        aria-label="Menú principal"
      >
        <div className="nav-drawer-head">
          <span className="card-title">Menú</span>
          <button type="button" className="icon-btn" aria-label="Cerrar menú" onClick={cerrarMenu}>
            <IconoCerrar />
          </button>
        </div>
        <div className="nav-drawer-links">
          {NAVEGACION.map((item) => (
            <NavLink
              key={item.ruta}
              to={item.ruta}
              end={item.fin}
              className={claseEnlace}
              onClick={salirDelDrawer}
            >
              {item.etiqueta}
            </NavLink>
          ))}
        </div>
      </nav>

      <main className="page" ref={mainRef} tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/importar" element={<WizardImport />} />
          <Route path="/alertas" element={<PanelAlertas />} />
          <Route path="/compras" element={<RecomendacionesCompras />} />
          <Route path="/chat" element={<ChatIA />} />
        </Routes>
      </main>

      {ubicacion.pathname !== "/chat" && (
        <button
          type="button"
          ref={botonChatRef}
          className={`chat-fab${chatAbierto ? " is-open" : ""}`}
          aria-label={chatAbierto ? "Cerrar asistente" : "Abrir asistente"}
          aria-expanded={chatAbierto}
          aria-controls="panel-chat"
          onClick={() => setChatAbierto((valor) => !valor)}
        >
          <IconoChat />
          <span className="chat-fab-label">{chatAbierto ? "Cerrar" : "Hablar con la IA"}</span>
        </button>
      )}

      {chatAbierto && <div className="chat-backdrop" aria-hidden="true" onClick={cerrarChat} />}

      <section
        id="panel-chat"
        className={`chat-panel${chatAbierto ? " is-open" : ""}`}
        role="dialog"
        aria-modal="false"
        aria-label="Asistente de Inventario-IA"
        /* Mismo criterio que el menú: `inert` evita ocultar el panel con el foco
           dentro de él. */
        inert={chatAbierto ? undefined : ""}
      >
        <ChatIA variante="panel" onCerrar={cerrarChat} />
      </section>
    </div>
  )
}

function App() {
  return (
    <Router>
      <Estructura />
    </Router>
  )
}

export default App
