import axios from 'axios'

// Vite redirige /api al backend (ver vite.config.js)
const api = axios.create({ timeout: 90000 })

// ─── Sistema ───────────────────────────────────────────────
export const getHealth = () => api.get('/health')

// ─── Análisis ──────────────────────────────────────────────
export const getKpis = () => api.get('/api/kpis')
export const getRotacion = (dias = 90) => api.get('/api/analisis/rotacion', { params: { dias } })
export const getRecomendaciones = () => api.get('/api/recomendaciones/compra')
export const getAlertas = () => api.get('/api/alertas')

// ─── Productos ─────────────────────────────────────────────
export const getProductos = () => api.get('/api/productos')

// ─── Importación ───────────────────────────────────────────
export function importarArchivo(archivo) {
  const formData = new FormData()
  formData.append('archivo', archivo)
  return api.post('/api/importar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// ─── Chat IA ───────────────────────────────────────────────
export const enviarPregunta = (pregunta) => api.post('/api/chat', { pregunta })
