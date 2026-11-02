import { useRef, useState } from 'react'
import { importarArchivo } from '../api.js'

export default function Importar() {
  const [cargando, setCargando] = useState(false)
  const [resultado, setResultado] = useState(null)
  const [error, setError] = useState('')
  const inputArchivo = useRef(null)

  async function subir(archivo) {
    if (!archivo) return
    setCargando(true)
    setError('')
    setResultado(null)
    try {
      const { data } = await importarArchivo(archivo)
      setResultado(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al importar el archivo')
    } finally {
      setCargando(false)
      if (inputArchivo.current) inputArchivo.current.value = ''
    }
  }

  return (
    <div>
      <h2>📥 Importar ventas desde Excel</h2>
      <p className="texto-secundario">
        Formatos: <strong>.xlsx</strong>, <strong>.xls</strong>, <strong>.csv</strong>.
        El archivo debe tener columnas de <strong>fecha</strong>, <strong>producto</strong>,
        <strong> cantidad</strong> y <strong>precio</strong> (se aceptan variantes de nombre:
        date/día, artículo/descripción, unidades, valor/monto…).
      </p>

      <label className="zona-suelta">
        <input
          ref={inputArchivo}
          type="file"
          accept=".xlsx,.xls,.csv"
          hidden
          onChange={(e) => subir(e.target.files?.[0])}
          disabled={cargando}
        />
        {cargando ? '⏳ Procesando archivo…' : '📄 Haz clic para elegir un archivo de ventas'}
      </label>

      {error && <div className="aviso error">{error}</div>}

      {resultado && (
        <div className="resultado-importacion">
          <h3>Resultado de la importación</h3>
          {resultado.mensaje && <div className="aviso error">{resultado.mensaje}</div>}
          <p>
            ✅ Filas importadas: <strong>{resultado.filas_ok}</strong>
            {resultado.filas_error > 0 && (
              <> · ⚠️ Filas con error: <strong>{resultado.filas_error}</strong></>
            )}
          </p>
          {resultado.errores?.length > 0 && (
            <details>
              <summary>Ver primeros errores</summary>
              <ul className="lista-errores">
                {resultado.errores.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </details>
          )}
          {resultado.filas_ok > 0 && (
            <p className="texto-secundario">
              Listo 🎉 Ve al <strong>Dashboard</strong> o pregunta al <strong>Asistente IA</strong>.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
