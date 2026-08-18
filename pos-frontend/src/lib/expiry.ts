// Mismo default que el backend (reports.services.near_expiry_stock_report,
// days=7) — no hay endpoint aparte para esto, ProductSearch/CartView
// evalúan el aviso localmente sobre el campo que ya trae el producto
// (Product.nearest_batch_expiration), así que el umbral vive aquí también.
const NEAR_EXPIRY_DAYS = 7

/** Mismo cuidado que formatDate: parsear los componentes a mano evita el
 * corrimiento de día por interpretar la fecha como medianoche UTC. */
function daysUntil(isoDateString: string): number {
  const [year, month, day] = isoDateString.split('-').map(Number)
  const expiration = new Date(year, month - 1, day)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((expiration.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
}

/** true si el producto tiene un lote vigente (no caducado) que caduca
 * dentro de los próximos NEAR_EXPIRY_DAYS — aviso no bloqueante, nunca
 * impide vender ni agregar al carrito. */
export function isNearExpiry(nearestBatchExpiration: string | null): boolean {
  if (nearestBatchExpiration === null) return false
  const days = daysUntil(nearestBatchExpiration)
  return days >= 0 && days <= NEAR_EXPIRY_DAYS
}
