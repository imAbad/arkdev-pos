// Guardado del JWT — localStorage alcanza para esta sesión (una sola
// pestaña, un solo cajero por dispositivo en la tienda). Refresh automático
// de token no está implementado todavía: el access token dura 8h
// (config.settings.SIMPLE_JWT), suficiente para un turno de trabajo; si
// expira a medio turno, ACCESS_TOKEN_EXPIRED fuerza logout (ver api-client.ts).
const ACCESS_TOKEN_KEY = 'arkdev_pos_access_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function setAccessToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token)
}

export function clearAccessToken(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
}
