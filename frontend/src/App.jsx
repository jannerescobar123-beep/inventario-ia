import { useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import Importar from './pages/Importar.jsx'
import Chat from './pages/Chat.jsx'

const PESTANAS = [
  { id: 'dashboard', nombre: '📊 Dashboard' },
  { id: 'importar', nombre: '📥 Importar' },
  { id: 'chat', nombre: '💬 Asistente IA' },
]

export default function App() {
  const [pestana, setPestana] = useState('dashboard')

  return (
    <div className="app">
      <header className="cabecera">
        <h1>🏪 Inventario-IA</h1>
        <span className="etiqueta">IA local · 100% offline</span>
      </header>

      <nav className="navegacion">
        {PESTANAS.map((p) => (
          <button
            key={p.id}
            className={`pestana ${pestana === p.id ? 'activa' : ''}`}
            onClick={() => setPestana(p.id)}
          >
            {p.nombre}
          </button>
        ))}
      </nav>

      <main className="contenido">
        {pestana === 'dashboard' && <Dashboard />}
        {pestana === 'importar' && <Importar />}
        {pestana === 'chat' && <Chat />}
      </main>
    </div>
  )
}
