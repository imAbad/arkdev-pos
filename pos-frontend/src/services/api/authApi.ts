import { apiClient } from '@/lib/api-client'
import type { SupervisorAuthorization, TokenPair } from '@/types/api'

export async function login(email: string, password: string): Promise<TokenPair> {
  const response = await apiClient.post<TokenPair>('/auth/token/', { email, password })
  return response.data
}

/** Punto 5: login alterno de mostrador (usuario + fecha de nacimiento) —
 * devuelve el mismo par de tokens que el login normal, ver
 * tenants.viewsets.UsernameLoginView. Más débil que contraseña a
 * propósito (ver AuthProvider.usernameLoginErrorMessage y
 * arquitectura_tecnica_pos.md §7) — coexiste con login(), no lo reemplaza. */
export async function loginWithUsername(username: string, dateOfBirth: string): Promise<TokenPair> {
  const response = await apiClient.post<TokenPair>('/auth/token/username/', {
    username,
    date_of_birth: dateOfBirth,
  })
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
