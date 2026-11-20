import { useCallback, useEffect, useRef, useState } from "react"
import api from "../../utils/api"

const FORMULARIO_VACIO = { nombre: "", lead_time_dias: 7, contacto: "", telefono: "" }

const Proveedores = () => {
  const [proveedores, setProveedores] = useState([])
  const [cargando, setCargando] = useState(true)
  const [errorCarga, setErrorCarga] = useState("")
  const [aviso, setAviso] = useState("")
  const [errorFormulario, setErrorFormulario] = useState("")
  const [formulario, setFormulario] = useState(FORMULARIO_VACIO)
  const [editandoId, setEditandoId] = useState(null)
  const [guardando, setGuardando] = useState(false)
  const [ocupadoId, setOcupadoId] = useState(null)
  const [confirmandoBaja, setConfirmandoBaja] = useState(null)

  const campoNombreRef = useRef(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    setErrorCarga("")
    try {
      setProveedores(await api.proveedores(false))
    } catch (e) {
      setErrorCarga(`No se pudo conectar con la API: ${e.message}`)
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  const cambiarCampo = (evento) => {
    const { name, value } = evento.target
    setFormulario((actual) => ({ ...actual, [name]: value }))
  }

  const limpiarFormulario = () => {
    setFormulario(FORMULARIO_VACIO)
    setEditandoId(null)
    setErrorFormulario("")
  }

  const enviar = async (evento) => {
    evento.preventDefault()
    setErrorFormulario("")
    setAviso("")

    const nombre = formulario.nombre.trim()
    const leadTime = Number(formulario.lead_time_dias)
    if (!nombre) {
      setErrorFormulario("El nombre del proveedor es obligatorio.")
      campoNombreRef.current?.focus()
      return
    }
    if (!Number.isInteger(leadTime) || leadTime < 1 || leadTime > 365) {
      setErrorFormulario("El tiempo de entrega debe ser un número entero entre 1 y 365 días.")
      return
    }

    const datos = {
      nombre,
      lead_time_dias: leadTime,
      contacto: formulario.contacto.trim() || null,
      telefono: formulario.telefono.trim() || null,
    }

    setGuardando(true)
    try {
      if (editandoId === null) {
        await api.crearProveedor(datos)
        setAviso(`Proveedor «${nombre}» creado.`)
      } else {
        await api.editarProveedor(editandoId, { ...datos, activo: true })
        setAviso(`Proveedor «${nombre}» actualizado.`)
      }
      limpiarFormulario()
      await cargar()
    } catch (e) {
      setErrorFormulario(e.message)
    } finally {
      setGuardando(false)
    }
  }

  const editar = (proveedor) => {
    setEditandoId(proveedor.id)
    setFormulario({
      nombre: proveedor.nombre,
      lead_time_dias: proveedor.lead_time_dias,
      contacto: proveedor.contacto ?? "",
      telefono: proveedor.telefono ?? "",
    })
    setErrorFormulario("")
    setAviso("")
    campoNombreRef.current?.focus()
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  const darDeBaja = async (proveedor) => {
    setOcupadoId(proveedor.id)
    setAviso("")
    try {
      await api.bajaProveedor(proveedor.id)
      setAviso(
        `Proveedor «${proveedor.nombre}» dado de baja. Sus productos vuelven al plazo de 7 días.`
      )
      setConfirmandoBaja(null)
      await cargar()
    } catch (e) {
      setErrorFormulario(e.message)
    } finally {
      setOcupadoId(null)
    }
  }

  const reactivar = async (proveedor) => {
    setOcupadoId(proveedor.id)
    setAviso("")
    try {
      await api.editarProveedor(proveedor.id, {
        nombre: proveedor.nombre,
        lead_time_dias: proveedor.lead_time_dias,
        contacto: proveedor.contacto,
        telefono: proveedor.telefono,
        activo: true,
      })
      setAviso(`Proveedor «${proveedor.nombre}» reactivado.`)
      await cargar()
    } catch (e) {
      setErrorFormulario(e.message)
    } finally {
      setOcupadoId(null)
    }
  }

  if (cargando) {
    return (
      <div className="loading-state">
        <span className="spinner" aria-hidden="true" />
        <span>Cargando proveedores…</span>
      </div>
    )
  }

  if (errorCarga) {
    return (
      <div className="error-state">
        <strong>Backend no disponible</strong>
        <span>{errorCarga}</span>
        <span className="state-hint">Comprueba que la API responde en el puerto 8000.</span>
        <button type="button" className="btn btn-primary" onClick={cargar}>
          Reintentar
        </button>
      </div>
    )
  }

  const activos = proveedores.filter((proveedor) => proveedor.activo).length

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Proveedores</h1>
        <p className="page-subtitle">
          El tiempo de entrega de cada proveedor alimenta las recomendaciones de compra: el punto
          de reorden y la fecha de llegada se calculan con él, no con un plazo fijo.
        </p>
      </div>

      <section className="surface-card bloque-formulario" aria-labelledby="titulo-formulario-proveedor">
        <div className="card-head">
          <h2 className="card-title" id="titulo-formulario-proveedor">
            {editandoId === null ? "Nuevo proveedor" : "Editar proveedor"}
          </h2>
          {editandoId !== null && (
            <button type="button" className="btn btn-ghost" onClick={limpiarFormulario}>
              Cancelar edición
            </button>
          )}
        </div>

        <form className="fila-formulario" onSubmit={enviar}>
          <label className="form-field">
            <span className="form-label">Nombre</span>
            <input
              ref={campoNombreRef}
              type="text"
              name="nombre"
              className="form-control"
              value={formulario.nombre}
              onChange={cambiarCampo}
              maxLength={200}
              required
              placeholder="Ferretería Paz"
              autoComplete="off"
            />
          </label>

          <label className="form-field">
            <span className="form-label">Tiempo de entrega (días)</span>
            <input
              type="number"
              name="lead_time_dias"
              className="form-control"
              value={formulario.lead_time_dias}
              onChange={cambiarCampo}
              min={1}
              max={365}
              step={1}
              required
            />
          </label>

          <label className="form-field">
            <span className="form-label">Contacto</span>
            <input
              type="text"
              name="contacto"
              className="form-control"
              value={formulario.contacto}
              onChange={cambiarCampo}
              maxLength={120}
              placeholder="Nombre de la persona"
              autoComplete="off"
            />
          </label>

          <label className="form-field">
            <span className="form-label">Teléfono</span>
            <input
              type="tel"
              name="telefono"
              className="form-control"
              value={formulario.telefono}
              onChange={cambiarCampo}
              maxLength={40}
              placeholder="600 000 000"
              autoComplete="off"
            />
          </label>

          <div className="fila-formulario-acciones">
            <button type="submit" className="btn btn-primary" disabled={guardando}>
              {guardando ? "Guardando…" : editandoId === null ? "Añadir proveedor" : "Guardar cambios"}
            </button>
          </div>
        </form>

        {errorFormulario && (
          <p className="aviso aviso-error" role="alert">
            {errorFormulario}
          </p>
        )}
      </section>

      <p className="aviso aviso-ok" role="status" aria-live="polite">
        {aviso}
      </p>

      <div className="section-head">
        <h2 className="section-title">Listado de proveedores</h2>
        <span className="count-chip">
          {activos} activo(s) · {proveedores.length} en total
        </span>
      </div>

      {proveedores.length === 0 ? (
        <div className="empty-state">
          <p className="mb-0">Todavía no hay proveedores.</p>
          <p className="state-hint">
            Añade el primero arriba y después asígnalo a sus productos desde el catálogo del Panel.
          </p>
        </div>
      ) : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Listado de proveedores">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Proveedor</th>
                <th scope="col" className="num">Entrega</th>
                <th scope="col">Contacto</th>
                <th scope="col">Teléfono</th>
                <th scope="col" className="num">Productos</th>
                <th scope="col">Estado</th>
                <th scope="col">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {proveedores.map((proveedor) => (
                <tr key={proveedor.id} className={proveedor.activo ? undefined : "fila-inactiva"}>
                  <td>{proveedor.nombre}</td>
                  <td className="num">{proveedor.lead_time_dias} días</td>
                  <td>{proveedor.contacto || "—"}</td>
                  <td>{proveedor.telefono || "—"}</td>
                  <td className="num">{proveedor.productos_asignados}</td>
                  <td>
                    <span className={`estado-chip ${proveedor.activo ? "estado-activo" : "estado-baja"}`}>
                      {proveedor.activo ? "Activo" : "De baja"}
                    </span>
                  </td>
                  <td>
                    <div className="acciones-fila">
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => editar(proveedor)}
                        disabled={ocupadoId === proveedor.id}
                      >
                        Editar
                      </button>

                      {proveedor.activo ? (
                        confirmandoBaja === proveedor.id ? (
                          <>
                            <button
                              type="button"
                              className="btn btn-soft"
                              onClick={() => darDeBaja(proveedor)}
                              disabled={ocupadoId === proveedor.id}
                            >
                              Confirmar baja
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost"
                              onClick={() => setConfirmandoBaja(null)}
                              disabled={ocupadoId === proveedor.id}
                            >
                              No
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-ghost"
                            onClick={() => {
                              setConfirmandoBaja(proveedor.id)
                              setAviso("")
                            }}
                            disabled={ocupadoId === proveedor.id}
                            aria-describedby={`baja-${proveedor.id}`}
                          >
                            Dar de baja
                          </button>
                        )
                      ) : (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => reactivar(proveedor)}
                          disabled={ocupadoId === proveedor.id}
                        >
                          Reactivar
                        </button>
                      )}
                    </div>
                    {confirmandoBaja === proveedor.id && (
                      <span className="state-hint" id={`baja-${proveedor.id}`}>
                        La baja conserva sus {proveedor.productos_asignados} producto(s): vuelven al
                        plazo de 7 días y se puede reactivar.
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="state-hint">
        Un producto sin proveedor usa el plazo por defecto de 7 días. Dar de baja un proveedor no
        borra nada: sus productos se quedan asignados y el plazo vuelve a 7 días.
      </p>
    </>
  )
}

export default Proveedores
