import { apiClient } from '@/lib/api-client'
import type { SupervisorAuthorization, TokenPair } from '@/types/api'

/** `identifier` acepta username O email — misma cuenta, misma
 * contraseña, un solo endpoint (ver tenants.serializers.
 * IdentifierTokenObtainPairSerializer). No hay una función de login
 * separada por identificador; quien llama decide qué escribió el
 * usuario en el único campo del formulario. */
export async function login(identifier: string, password: string): Promise<TokenPair> {
  const response = await apiClient.post<TokenPair>('/auth/token/', { identifier, password })
  return response.data
}

/** Punto 6/10: PIN/reautenticación de un supervisor SIN tocar la sesión
 * del cajero actual — emite un token corto de un solo uso que después se
 * consume en la acción sensible real (ej. sales.cancelSale). */
export async function requestSupervisorAuthorization(
  email: string,
  password: string,
  reason?: string,
): Promise<SupervisorAuthorization> {
  const response = await apiClient.post<SupervisorAuthorization>('/auth/authorize-exception/', {
    email,
    password,
    reason,
  })
  return response.data
}
