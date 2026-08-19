import type { Product } from '@/types/api'

export interface CartLine {
  product: Product
  quantity: number
}

/** Redondeo a centavos — coincide con `.quantize(Decimal('0.01'))` del
 * backend (sales.services.create_sale) para el caso normal. En un caso de
 * borde exacto a medio centavo, Python usa banker's rounding y esto no —
 * probabilidad prácticamente nula con precios reales de 2 decimales, no
 * se resuelve con una librería de precisión decimal en esta sesión (ver
 * arquitectura_tecnica_pos.md, nota de la pantalla de venta). Si el
 * backend llega a rechazar por esto, el error se muestra tal cual llega. */
function roundCents(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

export function lineSubtotal(line: CartLine): number {
  return line.quantity * Number(line.product.sale_price)
}

export function lineTax(line: CartLine): number {
  const taxRate = Number(line.product.tax_rate)
  return roundCents((lineSubtotal(line) * taxRate) / 100)
}

export function lineTotal(line: CartLine): number {
  return roundCents(lineSubtotal(line) + lineTax(line))
}

export function cartTotal(lines: CartLine[]): number {
  return roundCents(lines.reduce((sum, line) => sum + lineTotal(line), 0))
}

/** El producto usa cantidad fraccionaria (KG/GRAMO/LITRO) — el resto se
 * maneja como piezas enteras (ver catalog.Product.unit_type). */
export function allowsFractionalQuantity(product: Product): boolean {
  return product.unit_type === 'KG' || product.unit_type === 'GRAMO' || product.unit_type === 'LITRO'
}

/** Observación de sesión (ronda de 4 piezas, punto 2): bug real reportado
 * — se podía agregar al carrito una cantidad mayor a la existente y
 * avanzar hasta "Cobrar" antes de enterarse. `current_stock` (null si el
 * producto no usa control por lote, ver catalog.Product.requires_batch)
 * es el mismo dato que ProductSerializer ya expone y que
 * sales.services.create_sale valida al final — esto solo lo consulta
 * antes, no reimplementa la regla. Un producto sin control por lote
 * nunca "excede stock" aquí porque no hay ningún número real contra el
 * cual comparar (mismo hallazgo del punto 1: no se rastrea existencia
 * para ese caso). */
export function exceedsAvailableStock(line: CartLine): boolean {
  const stock = line.product.current_stock
  if (stock === null) return false
  return line.quantity > stock
}

export function cartHasStockIssues(lines: CartLine[]): boolean {
  return lines.some(exceedsAvailableStock)
}
