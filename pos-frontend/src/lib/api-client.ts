import axios, { AxiosError } from 'axios'
import { clearAccessToken, getAccessToken } from './auth-storage'

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

// Sesión expirada/rechazada a medio turno: no hay refresh automático
// todavía (ver auth-storage.ts) — se limpia el token y se manda de vuelta
// al login en el próximo render de AuthProvider.
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      clearAccessToken()
    }
    return Promise.reject(error)
  },
)

/** Extrae un mensaje de error legible de una respuesta de la API (formato
 * estandarizado por core.exceptions.api_exception_handler: {code, detail}). */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object') {
      const firstValue = Object.values(detail)[0]
      if (Array.isArray(firstValue) && typeof firstValue[0] === 'string') return firstValue[0]
      if (typeof firstValue === 'string') return firstValue
    }
  }
  return fallback
}
