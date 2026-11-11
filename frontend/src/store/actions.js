import {
  importacionCompletada,
  mensajeChat,
  resetearChat,
  seleccionarProducto as seleccionarProductoAction
} from "../reducers"

export const cargarDatosIniciales = () => ({ type: "inventario/cargarDatosIniciales" })

export const seleccionarProducto = (producto) => seleccionarProductoAction(producto)

export const resetear_chat = () => resetearChat()

export const registrar_mensaje_chat = (mensaje) => mensajeChat(mensaje)

export const registrar_importacion = (resultado) => importacionCompletada(resultado)

export async function enviar_mensaje_chat({ texto, contexto = {} }) {
  const consulta = texto.trim()
  const ventas = contexto.kpis?.ventas_totales

  if (!consulta) {
    return "Escribe una pregunta para que pueda ayudarte."
  }

  if (ventas) {
    return `Recibí tu consulta: “${consulta}”. Las ventas totales registradas son $${ventas.toLocaleString("es-CO")}.`
  }

  return `Recibí tu consulta: “${consulta}”. Aún no hay datos suficientes para generar una recomendación.`
}
