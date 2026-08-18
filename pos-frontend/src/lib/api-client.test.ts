// Generalización del mapeo de errores a español que corrigió el bug del
// login (ver AuthProvider.test.tsx) a TODA la app: red caída, 401 a medio
// uso, 500 genérico y el caso feliz (detail legible del backend) — mismo
// estándar de test, forzando la forma exacta de la respuesta.
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { apiClient, apiErrorMessage, onSessionExpired } from './api-client'
import { setAccessToken, clearAccessToken } from './auth-storage'
import { axiosErrorWithStatus, axiosNetworkError } from '@/test/fixtures'
import { server } from '@/test/server'
import { t } from '@/i18n'

const BASE = import.meta.env.VITE_API_BASE_URL

describe('apiErrorMessage', () => {
  it('mapea un error sin respuesta (red caída/timeout) al mensaje de conexión', () => {
    expect(apiErrorMessage(axiosNetworkError(), 'fallback específico de la pantalla')).toBe(t.common.errorNetwork)
  })

  it('mapea 401 al mensaje de sesión expirada, sin intentar leer detail crudo', () => {
    // Forma real de un token inválido/expirado — ver curl contra el
    // backend real: {"code":"InvalidToken","detail":{"detail":"Given
    // token not valid for any token type", ...}}. Si se leyera `detail`
    // aquí como en cualquier otro código, se filtraría texto en inglés.
    const error = axiosErrorWithStatus(401, {
      code: 'InvalidToken',
      detail: { detail: 'Given token not valid for any token type', code: 'token_not_valid' },
    })
    const message = apiErrorMessage(error, 'fallback')
    expect(message).toBe(t.common.errorSessionExpired)
    expect(message).not.toMatch(/token/i)
  })

  it('mapea cualquier 5xx a un mensaje humano genérico, nunca el detail crudo', () => {
    const error = axiosErrorWithStatus(500, '<html>Internal Server Error</html>')
    expect(apiErrorMessage(error, 'fallback')).toBe(t.common.errorServer)
  })

  it('lee detail como string cuando el backend lo manda así (caso feliz ya existente)', () => {
    const error = axiosErrorWithStatus(400, { detail: 'No hay suficiente stock de Arroz superextra 1kg.' })
    expect(apiErrorMessage(error, 'fallback')).toBe('No hay suficiente stock de Arroz superextra 1kg.')
  })

  it('usa el fallback de la pantalla si no hay nada legible en la respuesta', () => {
    const error = axiosErrorWithStatus(400, {})
    expect(apiErrorMessage(error, 'fallback específico')).toBe('fallback específico')
  })
})

describe('onSessionExpired', () => {
  it('se dispara cuando una request CON token recibe 401 (sesión expirada a medio uso)', async () => {
    setAccessToken('un-token-que-ya-expiró')
    server.use(http.get(`${BASE}/user-profiles/me/`, () => HttpResponse.json({ detail: 'expired' }, { status: 401 })))

    const listener = vi.fn()
    const unsubscribe = onSessionExpired(listener)
    try {
      await apiClient.get('/user-profiles/me/').catch(() => {})
      expect(listener).toHaveBeenCalledTimes(1)
    } finally {
      unsubscribe()
      clearAccessToken()
    }
  })

  it('NO se dispara cuando una request SIN token recibe 401 (login con credenciales inválidas)', async () => {
    clearAccessToken()
    server.use(http.post(`${BASE}/auth/token/`, () => HttpResponse.json({ detail: 'invalid' }, { status: 401 })))

    const listener = vi.fn()
    const unsubscribe = onSessionExpired(listener)
    try {
      await apiClient.post('/auth/token/', { email: 'a@a.com', password: 'x' }).catch(() => {})
      expect(listener).not.toHaveBeenCalled()
    } finally {
      unsubscribe()
    }
  })
})
