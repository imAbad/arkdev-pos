const currencyFormatter = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'MXN',
})

/** Los montos de la API llegan como string (DecimalField de DRF) — nunca
 * hacer aritmética directa sobre floats de JS con dinero, siempre pasar
 * por Number() solo al formatear para mostrar. */
export function formatCurrency(amount: string | number): string {
  const value = typeof amount === 'string' ? Number(amount) : amount
  return currencyFormatter.format(Number.isFinite(value) ? value : 0)
}

const dateTimeFormatter = new Intl.DateTimeFormat('es-MX', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

/** occurred_at/created_at de la API vienen en ISO 8601 (UTC) — se
 * formatean en la hora local de quien ve la pantalla. */
export function formatDateTime(isoString: string): string {
  return dateTimeFormatter.format(new Date(isoString))
}

const dateFormatter = new Intl.DateTimeFormat('es-MX', { dateStyle: 'medium' })

/** Para fechas puras sin hora (YYYY-MM-DD, ej. Batch.expiration_date) —
 * parsear los componentes a mano y construir la fecha en hora LOCAL, no
 * `new Date(isoDateString)` directo: eso la interpreta como medianoche
 * UTC, y en una zona con offset negativo (México, UTC-6) se mostraría un
 * día antes del real. */
export function formatDate(isoDateString: string): string {
  const [year, month, day] = isoDateString.split('-').map(Number)
  return dateFormatter.format(new Date(year, month - 1, day))
}
