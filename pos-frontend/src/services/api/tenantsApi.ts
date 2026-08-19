import { apiClient } from '@/lib/api-client'
import type { Branch, CompanySettings, Paginated, Role, UserProfile } from '@/types/api'

export async function getMyProfile(): Promise<UserProfile> {
  const response = await apiClient.get<UserProfile>('/user-profiles/me/')
  return response.data
}

export async function getBranch(branchId: number): Promise<Branch> {
  const response = await apiClient.get<Branch>(`/branches/${branchId}/`)
  return response.data
}

export async function listBranches(): Promise<Branch[]> {
  const response = await apiClient.get<Paginated<Branch>>('/branches/')
  return response.data.results
}

/** Un tenant siempre tiene exactamente una fila propia — el endpoint ya
 * viene acotado por TenantScopedQuerySet, no hace falta filtrar por id. */
export async function getMyCompanySettings(): Promise<CompanySettings | null> {
  const response = await apiClient.get<Paginated<CompanySettings>>('/company-settings/')
  return response.data.results[0] ?? null
}

/** Solo campos JSON — `logo` es un ImageField, se sube aparte con
 * FormData (ver updateCompanyLogo). El backend ya soportaba PATCH desde
 * antes (ModelViewSet completo); solo faltaba la pantalla y, se
 * encontró al construirla, el permiso: antes cualquier usuario
 * autenticado del tenant podía escribir aquí, ahora solo ADMINISTRADOR
 * (ver core.permissions.IsAdministratorOrReadOnly). */
export async function updateCompanySettings(
  id: number,
  patch: Partial<Pick<CompanySettings, 'business_name' | 'accent_color' | 'enabled_modules'>>,
): Promise<CompanySettings> {
  const response = await apiClient.patch<CompanySettings>(`/company-settings/${id}/`, patch)
  return response.data
}

/** Punto 12: logo real vía FormData/multipart — un ImageField no acepta
 * el mismo PATCH JSON que el resto de campos de CompanySettings. */
export async function updateCompanyLogo(id: number, file: File): Promise<CompanySettings> {
  const formData = new FormData()
  formData.append('logo', file)
  const response = await apiClient.patch<CompanySettings>(`/company-settings/${id}/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

// Punto 9 — gestión de usuarios, ADMINISTRADOR exclusivo (ver
// core.permissions.IsAdministrator en UserProfileViewSet).
export async function listUsers(): Promise<UserProfile[]> {
  const response = await apiClient.get<Paginated<UserProfile>>('/user-profiles/')
  return response.data.results
}

export interface CreateUserInput {
  password: string
  branch: number
  role: Role
  capabilities?: UserProfile['capabilities']
  // Único identificador obligatorio — sirve por sí solo para entrar
  // (misma contraseña que si además tuviera email). email/date_of_birth
  // son opcionales: email como segundo identificador de login si se
  // quiere, date_of_birth solo como dato de perfil (nunca para
  // autenticar, ver tenants.models.UserProfile.date_of_birth).
  username: string
  email?: string
  date_of_birth?: string
}

export async function createUser(input: CreateUserInput): Promise<UserProfile> {
  const response = await apiClient.post<UserProfile>('/user-profiles/', input)
  return response.data
}

export async function updateUser(
  id: number,
  patch: Partial<Pick<UserProfile, 'branch' | 'role' | 'capabilities'>>,
): Promise<UserProfile> {
  const response = await apiClient.patch<UserProfile>(`/user-profiles/${id}/`, patch)
  return response.data
}

export async function deactivateUser(id: number): Promise<UserProfile> {
  const response = await apiClient.post<UserProfile>(`/user-profiles/${id}/deactivate/`)
  return response.data
}

export async function reactivateUser(id: number): Promise<UserProfile> {
  const response = await apiClient.post<UserProfile>(`/user-profiles/${id}/reactivate/`)
  return response.data
}
