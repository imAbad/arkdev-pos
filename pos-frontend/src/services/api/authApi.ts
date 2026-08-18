import { apiClient } from '@/lib/api-client'
import type { SupervisorAuthorization, TokenPair } from '@/types/api'

export async function login(email: string, password: string): Promise<TokenPair> {
  const response = await apiClient.post<TokenPair>('/auth/token/', { email, password })
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
