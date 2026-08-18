import type { UserProfile } from '@/types/api'

/** ADMINISTRADOR o CAJERO con can_authorize_exceptions — "Supervisor" no
 * es un rol propio (ver decisiones_post_auditoria.md §5), es este mismo
 * criterio ya usado en el backend para el override de cierre de turno
 * ajeno y ahora también para reportes/exportación/inventario. Un solo
 * lugar para no repetir esta condición por componente. */
export function isAdministratorOrSupervisor(profile: UserProfile | null): boolean {
  if (profile === null) return false
  return profile.role === 'ADMINISTRADOR' || Boolean(profile.capabilities.can_authorize_exceptions)
}

export function isAdministrator(profile: UserProfile | null): boolean {
  return profile !== null && profile.role === 'ADMINISTRADOR'
}
