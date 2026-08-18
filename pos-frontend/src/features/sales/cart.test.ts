import { describe, expect, it } from 'vitest'
import { makeProduct } from '@/test/fixtures'
import { allowsFractionalQuantity, cartTotal, lineSubtotal, lineTax, lineTotal, type CartLine } from './cart'

describe('cart math (sin mocks — misma lógica que sales.services.create_sale)', () => {
  it('calcula el subtotal de una línea como cantidad * precio', () => {
    const line: CartLine = { product: makeProduct({ sale_price: '18.00' }), quantity: 2 }
    expect(lineSubtotal(line)).toBe(36)
  })

  it('calcula el IVA de una línea al 16%', () => {
    const line: CartLine = { product: makeProduct({ sale_price: '18.00', tax_rate: '16.00' }), quantity: 1 }
    expect(lineTax(line)).toBeCloseTo(2.88, 2)
    expect(lineTotal(line)).toBeCloseTo(20.88, 2)
  })

  it('un producto exento (tax_rate 0) no agrega impuesto', () => {
    const line: CartLine = { product: makeProduct({ sale_price: '26.50', tax_rate: '0.00' }), quantity: 1 }
    expect(lineTax(line)).toBe(0)
    expect(lineTotal(line)).toBe(26.5)
  })

  it('suma correctamente tasas de IVA mixtas en el mismo carrito (16% y 0%)', () => {
    // Mismo escenario probado manualmente contra el backend real: refresco
    // gravado (16%) + leche exenta (0%) -> total $47.38.
    const lines: CartLine[] = [
      { product: makeProduct({ id: 1, sale_price: '18.00', tax_rate: '16.00' }), quantity: 1 },
      { product: makeProduct({ id: 2, sale_price: '26.50', tax_rate: '0.00' }), quantity: 1 },
    ]
    expect(cartTotal(lines)).toBeCloseTo(47.38, 2)
  })

  it('multiplica cantidad y precio antes de aplicar el IVA', () => {
    const lines: CartLine[] = [{ product: makeProduct({ sale_price: '18.00', tax_rate: '16.00' }), quantity: 3 }]
    // 3 * 18.00 = 54.00 subtotal, + 16% = 62.64
    expect(cartTotal(lines)).toBeCloseTo(62.64, 2)
  })

  it('cantidad fraccionaria (KG) calcula correctamente el total', () => {
    const lines: CartLine[] = [
      { product: makeProduct({ unit_type: 'KG', sale_price: '40.00', tax_rate: '0.00' }), quantity: 0.75 },
    ]
    expect(cartTotal(lines)).toBeCloseTo(30, 2)
  })

  it('un carrito vacío totaliza cero', () => {
    expect(cartTotal([])).toBe(0)
  })

  it('allowsFractionalQuantity es true solo para KG/GRAMO/LITRO', () => {
    expect(allowsFractionalQuantity(makeProduct({ unit_type: 'KG' }))).toBe(true)
    expect(allowsFractionalQuantity(makeProduct({ unit_type: 'GRAMO' }))).toBe(true)
    expect(allowsFractionalQuantity(makeProduct({ unit_type: 'LITRO' }))).toBe(true)
    expect(allowsFractionalQuantity(makeProduct({ unit_type: 'PIEZA' }))).toBe(false)
    expect(allowsFractionalQuantity(makeProduct({ unit_type: 'PAQUETE' }))).toBe(false)
    expect(allowsFractionalQuantity(makeProduct({ unit_type: 'SERVICIO' }))).toBe(false)
  })
})
