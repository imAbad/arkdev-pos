// Fija el mapeo de errores HTTP -> mensaje en español que corrigió el bug
// real encontrado al probar el login a mano contra el backend: SimpleJWT
// devuelve "No active account found with the given credentials" (inglés,
// sin pasar por core.exceptions.api_exception_handler) y NUNCA debe
// mostrarse tal cual — ver el principio de diseño de nada de inglés/jerga
// visible. Este test evita que alguien lo reintroduzca sin darse cuenta.
import axios, { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { loginErrorMessage } from './AuthProvider'
import { t } from '@/i18n'

function axiosErrorWithStatus(status: number, data: unknown = {}): AxiosError {
  return new AxiosError(
    'Request failed',
    'ERR_BAD_REQUEST',
    undefined,
    undefined,
    {
      status,
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
      data,
    },
  )
}

describe('loginErrorMessage', () => {
  it('mapea 401 (credenciales inválidas de SimpleJWT) a un mensaje en español', () => {
    const error = axiosErrorWithStatus(401, {
      detail: 'No active account found with the given credentials',
    })
    expect(loginErrorMessage(error)).toBe(t.login.errorInvalid)
  })

  it('nunca deja pasar el texto crudo en inglés del backend', () => {
    const error = axiosErrorWithStatus(401, {
      detail: 'No active account found with the given credentials',
    })
    const message = loginErrorMessage(error)
    expect(message).not.toMatch(/no active account/i)
    expect(message).not.toBe('No active account found with the given credentials')
  })

  it('mapea cualquier otro error (500, red caída) a un mensaje genérico en español', () => {
    expect(loginErrorMessage(axiosErrorWithStatus(500))).toBe(t.login.errorGeneric)
    expect(loginErrorMessage(new Error('Network Error'))).toBe(t.login.errorGeneric)
    expect(loginErrorMessage(undefined)).toBe(t.login.errorGeneric)
  })

  it('reconoce errores de axios reales, no solo instancias construidas a mano', () => {
    expect(axios.isAxiosError(axiosErrorWithStatus(401))).toBe(true)
  })
})
