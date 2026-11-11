// Cliente HTTP hacia la API local de Inventario-IA (ADR-001: todo corre en el PC)
const BASE_URL = "http://127.0.0.1:8000"

async function pedir(ruta, opciones = {}) {
  const respuesta = await fetch(`${BASE_URL}${ruta}`, opciones)
  if (!respuesta.ok) {
    let detalle = `Error ${respuesta.status}`
    try {
      const cuerpo = await respuesta.json()
      detalle = cuerpo.detail || detalle
    } catch {
      // respuesta sin cuerpo JSON
    }
    throw new Error(detalle)
  }
  return respuesta.json()
}

export const api = {
  health: () => pedir("/health"),
  kpis: () => pedir("/api/kpis"),
  alertas: () => pedir("/api/alertas"),
  productos: () => pedir("/api/productos"),
  rotacion: () => pedir("/api/rotacion"),
  recomendaciones: () => pedir("/api/recomendaciones"),

  importar: (archivo) => {
    const datos = new FormData()
    datos.append("file", archivo)
    return pedir("/api/importar", { method: "POST", body: datos })
  },

  chat: (mensaje, historial = []) =>
    pedir("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje, historial }),
    }),
}

export default api
