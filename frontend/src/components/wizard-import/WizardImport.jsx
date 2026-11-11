import { useState } from "react"
import api from "../../utils/api"

const EXTENSIONES = ["csv", "xlsx", "xls"]

const WizardImport = () => {
  const [archivo, setArchivo] = useState(null)
  const [estado, setEstado] = useState("listo")
  const [resultado, setResultado] = useState(null)
  const [error, setError] = useState("")

  const manejarArchivo = (event) => {
    const seleccionado = event.target.files?.[0]
    if (!seleccionado) return

    setError("")
    const extension = seleccionado.name.split(".").pop().toLowerCase()
    if (!EXTENSIONES.includes(extension)) {
      setArchivo(null)
      setEstado("error")
      setError("Formato no soportado. Usa un archivo .csv, .xlsx o .xls")
      return
    }

    setArchivo(seleccionado)
    setEstado("listo")
  }

  const procesarImportacion = async () => {
    if (!archivo) return
    setEstado("importando")
    setError("")
    try {
      const resumen = await api.importar(archivo)
      setResultado(resumen)
      setEstado("completado")
    } catch (e) {
      setEstado("error")
      setError(e.message)
    }
  }

  const reiniciar = () => {
    setArchivo(null)
    setResultado(null)
    setError("")
    setEstado("listo")
  }

  const pasoSeleccion = estado === "completado" || Boolean(archivo)
  const pasoImportar = estado === "completado" || (Boolean(archivo) && estado === "listo")

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Importar tus ventas</h1>
        <p className="page-subtitle">
          Sube el archivo del negocio. Si el Excel trae una hoja «productos», se importa antes para
          emparejar el catálogo (ADR-003).
        </p>
      </div>

      <div className="wizard-steps">
        <div className={`wizard-step ${pasoSeleccion ? "is-done" : "is-active"}`}>
          <span>1</span> <span>Seleccionar archivo</span>
        </div>
        <div className={`wizard-step ${pasoImportar ? "is-done" : archivo ? "is-active" : ""}`}>
          <span>2</span> <span>Importar</span>
        </div>
        <div className={`wizard-step ${estado === "completado" || estado === "error" ? "is-active" : ""}`}>
          <span>3</span> <span>Resultado</span>
        </div>
      </div>

      {estado !== "completado" && (
        <>
          <label className="upload-zone" htmlFor="archivo-ventas">
            <strong>{archivo ? archivo.name : "Selecciona el archivo de ventas"}</strong>
            <span className="state-hint">
              {archivo
                ? `${Math.max(1, Math.round(archivo.size / 1024))} KB · listo para importar`
                : "Arrastra el archivo aquí o pulsa para elegirlo (.csv, .xlsx, .xls)"}
            </span>
            <input
              id="archivo-ventas"
              className="visually-hidden"
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={manejarArchivo}
              disabled={estado === "importando"}
            />
          </label>

          <p className="state-hint">
            CSV: columnas <code>fecha,producto,cantidad,precio</code>. Excel: hoja <code>ventas</code> y
            hoja opcional <code>productos</code>.
          </p>

          {archivo && estado !== "importando" && (
            <button type="button" className="btn btn-primary btn-lg" onClick={procesarImportacion}>
              Importar datos
            </button>
          )}

          {estado === "importando" && (
            <div className="loading-state">
              <span className="spinner" aria-hidden="true" />
              <span>Procesando archivo…</span>
            </div>
          )}
        </>
      )}

      {estado === "completado" && resultado && (
        <div className="surface-card">
          <div className="card-head">
            <h2 className="card-title">Importación completada</h2>
            <span className={`urgency-chip ${resultado.errores?.length > 0 ? "urg-medio" : "urg-bajo"}`}>
              {resultado.errores?.length > 0 ? `${resultado.errores.length} aviso(s)` : "sin errores"}
            </span>
          </div>

          <div className="stat-grid">
            <div className="stat-card">
              <span className="stat-label">Productos creados</span>
              <div className="stat-value num">{resultado.productos_creados}</div>
            </div>
            <div className="stat-card">
              <span className="stat-label">Productos actualizados</span>
              <div className="stat-value num">{resultado.productos_actualizados}</div>
            </div>
            <div className="stat-card">
              <span className="stat-label">Ventas registradas</span>
              <div className="stat-value num">{resultado.total_ventas}</div>
            </div>
          </div>

          {resultado.errores?.length > 0 && (
            <details>
              <summary className="state-hint">{resultado.errores.length} error(es) de validación</summary>
              <ul>
                {resultado.errores.slice(0, 20).map((err, indice) => (
                  <li key={indice}>
                    Fila {err.fila}: {err.motivo ?? err.motivos?.join(", ")}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <button type="button" className="btn btn-ghost btn-lg" onClick={reiniciar}>
            Importar otro archivo
          </button>
        </div>
      )}

      {estado === "error" && (
        <div className="error-state">
          <strong>No se pudo importar</strong>
          <span>{error}</span>
          <span className="state-hint">Comprueba el formato del archivo y que la API esté activa.</span>
          <button type="button" className="btn btn-primary" onClick={reiniciar}>
            Intentar de nuevo
          </button>
        </div>
      )}
    </>
  )
}

export default WizardImport
