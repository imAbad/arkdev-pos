import { apiClient } from '@/lib/api-client'
import type { Branch, CompanySettings, Paginated, UserProfile } from '@/types/api'

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
