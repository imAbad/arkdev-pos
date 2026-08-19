import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { makeProduct } from '@/test/fixtures'
import { t } from '@/i18n'
import { CartView } from './CartView'
import type { CartLine } from './cart'

// Bug real reportado: el input de cantidad dejaba escribir fracciones
// (1.1, 1.2…) para productos PIEZA, que se cuentan en enteros — ver
// catalog.Product.requires_integer_quantity / sales.services.create_sale
// en el backend. Estos tests fijan que el frontend ni siquiera deja
// escribir el punto decimal para PIEZA/PAQUETE/SERVICIO, y sí lo permite
// para KG/GRAMO/LITRO.
//
// fireEvent.keyDown en vez de userEvent.type: un <input type="number">
// en jsdom ya descarta por su cuenta cualquier tecleo que deje un valor
// intermedio inválido (ej. "1."), sin disparar onChange, sea cual sea
// nuestro código — probar la restricción tecleando de verdad no
// discrimina si la restricción la puso nuestro preventDefault o jsdom.
// fireEvent.keyDown() devuelve `false` si algún handler llamó
// preventDefault() — eso sí prueba directamente nuestro código.
describe('CartView — restricción de cantidad por unit_type', () => {
  function renderCart(product: ReturnType<typeof makeProduct>, quantity = 1) {
    const line: CartLine = { product, quantity }
    const onChangeQuantity = vi.fn()
    const { unmount } = render(<CartView lines={[line]} onChangeQuantity={onChangeQuantity} onRemove={() => {}} />)
    return { onChangeQuantity, unmount }
  }

  it('bloquea la tecla "." (y ",") para un producto PIEZA', () => {
    const product = makeProduct({ unit_type: 'PIEZA' })
    renderCart(product)
    const input = screen.getByLabelText(t.sale.quantity) as HTMLInputElement

    expect(fireEvent.keyDown(input, { key: '.' })).toBe(false)
    expect(fireEvent.keyDown(input, { key: ',' })).toBe(false)
    expect(input).toHaveAttribute('step', '1')
  })

  it('redondea a entero una cantidad fraccionaria que llega por otra vía (ej. pegar texto) para PIEZA', () => {
    const product = makeProduct({ unit_type: 'PIEZA' })
    const { onChangeQuantity } = renderCart(product)

    const input = screen.getByLabelText(t.sale.quantity) as HTMLInputElement
    fireChange(input, '1.7')

    expect(onChangeQuantity).toHaveBeenCalledWith(product.id, 2)
  })

  it('no bloquea la tecla "." para un producto KG', () => {
    const product = makeProduct({ unit_type: 'KG' })
    const { onChangeQuantity } = renderCart(product)
    const input = screen.getByLabelText(t.sale.quantity) as HTMLInputElement

    expect(fireEvent.keyDown(input, { key: '.' })).toBe(true)
    expect(input).toHaveAttribute('step', '0.1')

    fireChange(input, '0.75')
    expect(onChangeQuantity).toHaveBeenLastCalledWith(product.id, 0.75)
  })

  it('PAQUETE y SERVICIO también quedan restringidos a enteros, igual que PIEZA', () => {
    for (const unitType of ['PAQUETE', 'SERVICIO'] as const) {
      const product = makeProduct({ id: unitType === 'PAQUETE' ? 10 : 11, unit_type: unitType })
      const { onChangeQuantity, unmount } = renderCart(product)
      const input = screen.getByLabelText(t.sale.quantity) as HTMLInputElement

      expect(fireEvent.keyDown(input, { key: '.' })).toBe(false)
      fireChange(input, '2.5')
      expect(onChangeQuantity).toHaveBeenCalledWith(product.id, 3)
      unmount()
    }
  })
})

function fireChange(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
  setter.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

// Observación de sesión (ronda de 4 piezas, punto 2): bug real reportado
// — se avisaba de stock insuficiente hasta "Cobrar", no al capturar la
// cantidad. Estos tests fijan el aviso inmediato con el número real.
describe('CartView — aviso temprano de stock insuficiente', () => {
  it('muestra "Solo hay N disponibles" cuando la cantidad supera el stock', () => {
    const line: CartLine = { product: makeProduct({ current_stock: 20 }), quantity: 73 }
    render(<CartView lines={[line]} onChangeQuantity={() => {}} onRemove={() => {}} />)

    expect(screen.getByRole('alert')).toHaveTextContent(`${t.sale.stockExceededPrefix} 20 ${t.sale.stockExceededSuffix}`)
  })

  it('no muestra ningún aviso cuando la cantidad está dentro del stock', () => {
    const line: CartLine = { product: makeProduct({ current_stock: 20 }), quantity: 5 }
    render(<CartView lines={[line]} onChangeQuantity={() => {}} onRemove={() => {}} />)

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('no muestra ningún aviso para un producto sin control por lote (current_stock null)', () => {
    const line: CartLine = { product: makeProduct({ current_stock: null }), quantity: 999 }
    render(<CartView lines={[line]} onChangeQuantity={() => {}} onRemove={() => {}} />)

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
