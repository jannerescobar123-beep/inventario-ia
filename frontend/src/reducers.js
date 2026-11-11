import { createSlice } from "@reduxjs/toolkit"

const initialState = {
  kpis: {
    ventas_totales: 125470,
    ticket_promedio: 890,
    unidades_vendidas: 142,
    margen_total: 28500,
    top_productos: [
      { nombre: "Martillo profesional", cantidad: 45 },
      { nombre: "Cincel de acero", cantidad: 32 },
      { nombre: "Cable eléctrico 5 m", cantidad: 28 }
    ]
  },
  loading: false,
  error: null,
  importacion: {
    productos_creados: 0,
    productos_actualizados: 0,
    total_ventas: 0,
    ultimas_importaciones: []
  },
  alertas: {
    riesgo_agotamiento: [],
    ultimo_check: null
  },
  chat: {
    historial: [],
    esperando: false
  },
  productoSeleccionado: null
}

const inventarioSlice = createSlice({
  name: "inventario",
  initialState,
  reducers: {
    kpisSolicitar: (state) => {
      state.loading = true
      state.error = null
    },
    kpisExito: (state, action) => {
      state.kpis = action.payload
      state.loading = false
    },
    kpisError: (state, action) => {
      state.error = action.payload
      state.loading = false
    },
    importacionCompletada: (state, action) => {
      const resultado = action.payload
      state.importacion.productos_creados = resultado.productos_creados ?? 0
      state.importacion.productos_actualizados = resultado.productos_actualizados ?? 0
      state.importacion.total_ventas = resultado.total_ventas ?? 0
      state.importacion.ultimas_importaciones.unshift({
        fecha: new Date().toISOString(),
        ...resultado
      })
      state.importacion.ultimas_importaciones = state.importacion.ultimas_importaciones.slice(0, 5)
    },
    alertasActualizadas: (state, action) => {
      state.alertas.riesgo_agotamiento = action.payload ?? []
      state.alertas.ultimo_check = new Date().toISOString()
    },
    mensajeChat: (state, action) => {
      state.chat.historial.push(action.payload)
    },
    resetearChat: (state) => {
      state.chat.historial = []
    },
    seleccionarProducto: (state, action) => {
      state.productoSeleccionado = action.payload
    }
  }
})

export const {
  kpisSolicitar,
  kpisExito,
  kpisError,
  importacionCompletada,
  alertasActualizadas,
  mensajeChat,
  resetearChat,
  seleccionarProducto
} = inventarioSlice.actions

export default inventarioSlice.reducer
