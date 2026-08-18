import axios, { AxiosError } from 'axios'
import { clearAccessToken, getAccessToken } from './auth-storage'
import { t } from '@/i18n'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
})

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Quien escuche esto decide qué hacer con una sesión que dejó de ser
// válida a medio uso (AuthProvider: limpiar estado y mandar al login con
// un aviso) — separado del interceptor para no acoplar lib/api-client.ts
// (sin estado de React) a AuthProvider (con estado de React).
type SessionExpiredListener = () => void
const sessionExpiredListeners = new Set<SessionExpiredListener>()

export function onSessionExpired(listener: SessionExpiredListener): () => void {
  sessionExpiredListeners.add(listener)
  return () => sessionExpiredListeners.delete(listener)
}

// Sesión expirada/rechazada a medio turno: no hay refresh automático
// todavía (ver auth-storage.ts) — se limpia el token y se avisa a quien
// esté escuchando. Solo cuenta como "sesión expirada" si la request que
// falló SÍ llevaba un token (si no lo llevaba, es un login normal con
// credenciales inválidas — AuthProvider.loginErrorMessage ya cubre ese
// caso por separado, no se debe disparar este aviso también ahí).
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      const hadToken = Boolean(error.config?.headers?.Authorization)
      clearAccessToken()
      if (hadToken) {
        sessionExpiredListeners.forEach((listener) => listener())
      }
    }
    return Promise.reject(error)
  },
)

/** Extrae un mensaje de error legible de una respuesta de la API (formato
 * estandarizado por core.exceptions.api_exception_handler: {code, detail}).
 * Prioriza los casos que nunca deben mostrarse tal cual antes de intentar
 * leer `detail`:
 * - sin respuesta del servidor (red caída, timeout, CORS) -> mensaje de
 *   conexión, no el fallback específico de la pantalla que llamó.
 * - 401 -> igual que el bug de login ya corregido (SimpleJWT devuelve
 *   texto en inglés sin pasar por el exception_handler), nunca se intenta
 *   leer `detail` de un 401.
 * - 500 exacto -> mensaje genérico humano, nunca el detail crudo del
 *   backend (puede ser HTML de la página de error de Django, no JSON:
 *   es el único código que Django/DRF genera automático ante una
 *   excepción no manejada, nunca lo devuelve código propio a propósito).
 * - 502/503/504 -> SÍ se lee `detail`: a diferencia de 500, ningún código
 *   de este proyecto los produce por accidente — solo aparecen cuando una
 *   vista los devuelve a propósito con un mensaje ya pensado para
 *   mostrarse (ej. sales.views.send_ticket_email cuando el SMTP falla),
 *   igual de seguro que cualquier 400. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return t.common.errorNetwork
    if (error.response.status === 401) return t.common.errorSessionExpired
    if (error.response.status === 500) return t.common.errorServer

    const detail = error.response.data?.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object') {
      const firstValue = Object.values(detail)[0]
      if (Array.isArray(firstValue) && typeof firstValue[0] === 'string') return firstValue[0]
      if (typeof firstValue === 'string') return firstValue
    }
  }
  return fallback
}
