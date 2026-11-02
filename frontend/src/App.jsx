import { useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import Productos from './pages/Productos.jsx'
import Importar from './pages/Importar.jsx'
import Chat from './pages/Chat.jsx'

const PAGINAS = [
  { id: 'dashboard', icono: '📊', nombre: 'Dashboard', descripcion: 'Resumen general del negocio' },
  { id: 'productos', icono: '📦', nombre: 'Productos', descripcion: 'Catálogo y estado de stock' },
  { id: 'importar', icono: '📥', nombre: 'Importar', descripcion: 'Cargar ventas desde Excel' },
  { id: 'chat', icono: '💬', nombre: 'Asistente IA', descripcion: 'Pregunta sobre tu negocio' },
]

export default function App() {
  const [paginaActual, setPaginaActual] = useState('dashboard')
  const pagina = PAGINAS.find((p) => p.id === paginaActual)

  return (
    <div className="layout">
      <nav className="barra-lateral">
        <div className="marca">
          <span className="marca-logo">🏪</span>
          <div>
            <span className="marca-nombre">Inventario-IA</span>
            <span className="marca-sub">IA local · 100% offline</span>
          </div>
        </div>

        <ul className="menu">
          {PAGINAS.map((p) => (
            <li key={p.id}>
              <button
                className={`menu-item ${paginaActual === p.id ? 'activo' : ''}`}
                onClick={() => setPaginaActual(p.id)}
              >
                <span className="menu-icono">{p.icono}</span>
                <span>
                  <span className="menu-nombre">{p.nombre}</span>
                  <span className="menu-descripcion">{p.descripcion}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div className="pie-lateral">
          <span className="punto-verde" /> Datos en tu PC · SQLite
        </div>
      </nav>

      <main className="contenido">
        <header className="cabecera-pagina">
          <h1>{pagina.icono} {pagina.nombre}</h1>
          <p className="subtitulo-pagina">{pagina.descripcion}</p>
        </header>

        {paginaActual === 'dashboard' && <Dashboard />}
        {paginaActual === 'productos' && <Productos />}
        {paginaActual === 'importar' && <Importar />}
        {paginaActual === 'chat' && <Chat />}
      </main>
    </div>
  )
}
