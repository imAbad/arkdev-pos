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
