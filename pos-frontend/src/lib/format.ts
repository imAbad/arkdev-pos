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
