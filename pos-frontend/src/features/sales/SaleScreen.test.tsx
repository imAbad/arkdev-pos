import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/react'
import { renderWithAuth } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeProduct, makeSale, makeShift } from '@/test/fixtures'
import { t } from '@/i18n'
import { SaleScreen } from './SaleScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const PRODUCTS_URL = `${BASE}/products/`
const CREATE_SALE_URL = `${BASE}/sales/create-sale/`

const REFRESCO = makeProduct({ id: 1, name: 'Refresco de cola 600ml', sku: 'REF-600', sale_price: '18.00', tax_rate: '16.00' })
const LECHE = makeProduct({ id: 2, name: 'Leche entera 1L', sku: 'LEC-1L', sale_price: '26.50', tax_rate: '0.00' })

function mockSearch(byQuery: Record<string, ReturnType<typeof makeProduct>[]>) {
  server.use(
    http.get(PRODUCTS_URL, ({ request }) => {
      const query = new URL(request.url).searchParams.get('search') ?? ''
      const results = byQuery[query] ?? []
      return HttpResponse.json({ count: results.length, next: null, previous: null, results })
    }),
  )
}

async function addProductToCart(user: ReturnType<typeof userEvent.setup>, query: string, productName: string) {
  await user.type(screen.getByLabelText(t.sale.searchLabel), query)
  const result = await screen.findByRole('button', { name: new RegExp(productName) })
  await user.click(result)
}

describe('SaleScreen', () => {
  it('agrega un producto encontrado en la búsqueda al carrito', async () => {
    mockSearch({ refresco: [REFRESCO] })
    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift()} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')

    expect(screen.getByText('Refresco de cola 600ml')).toBeInTheDocument()
    expect(screen.queryByText(t.sale.emptyCart)).not.toBeInTheDocument()
  })

  it('la cantidad es editable y el total de la línea se recalcula', async () => {
    mockSearch({ refresco: [REFRESCO] })
    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift()} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')

    const quantityInput = screen.getByLabelText(t.sale.quantity)
    await user.clear(quantityInput)
    await user.type(quantityInput, '3')

    // 3 * 18.00 = 54.00 subtotal, + 16% IVA = 62.64 (aparece en la línea Y
    // en el total general, porque es el único producto en el carrito).
    await waitFor(() => expect(screen.getAllByText('$62.64')).toHaveLength(2))
  })

  it('calcula el IVA mixto (16% y 0% en el mismo carrito) — mismo caso probado manualmente contra el backend', async () => {
    mockSearch({ refresco: [REFRESCO], leche: [LECHE] })
    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift()} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')
    await addProductToCart(user, 'leche', 'Leche entera 1L')

    // 18.00 * 1.16 + 26.50 * 1.00 = 20.88 + 26.50 = 47.38
    expect(await screen.findByText('$47.38')).toBeInTheDocument()
  })

  it('calcula el cambio a entregar cuando el pago es en efectivo', async () => {
    mockSearch({ refresco: [REFRESCO] })
    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift()} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')
    // Total: $20.88 — método Efectivo ya es el default.
    const cashInput = screen.getByLabelText(t.sale.cashReceived)
    await user.clear(cashInput)
    await user.type(cashInput, '25')

    await waitFor(() => expect(screen.getByText('$4.12')).toBeInTheDocument())
  })

  it('no permite cobrar si el efectivo recibido es menor al total', async () => {
    mockSearch({ refresco: [REFRESCO] })
    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift()} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')
    const cashInput = screen.getByLabelText(t.sale.cashReceived)
    await user.clear(cashInput)
    await user.type(cashInput, '5')

    expect(await screen.findByText(t.sale.changeInsufficient)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.sale.charge })).toBeDisabled()
  })

  it('al cobrar exitosamente muestra la confirmación con el total y el cambio correctos', async () => {
    mockSearch({ refresco: [REFRESCO] })
    let capturedBody: unknown = null
    server.use(
      http.post(CREATE_SALE_URL, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(
          makeSale({ subtotal: '18.00', tax_amount: '2.88', total: '20.88' }),
          { status: 201 },
        )
      }),
    )

    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift({ id: 42 })} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')
    const cashInput = screen.getByLabelText(t.sale.cashReceived)
    await user.clear(cashInput)
    await user.type(cashInput, '25')
    await user.click(screen.getByRole('button', { name: t.sale.charge }))

    expect(await screen.findByText(t.confirmation.title)).toBeInTheDocument()
    expect(screen.getByText('$20.88')).toBeInTheDocument() // total cobrado
    expect(screen.getByText('$4.12')).toBeInTheDocument() // cambio entregado

    expect(capturedBody).toMatchObject({
      cash_shift: 42,
      details: [{ product_id: REFRESCO.id, quantity: '1.000', unit_price: '18.00' }],
      payments: [{ method: 'CASH', amount: '20.88' }],
    })
  })

  it('"Nueva venta" desde la confirmación regresa al carrito vacío', async () => {
    mockSearch({ refresco: [REFRESCO] })
    server.use(http.post(CREATE_SALE_URL, () => HttpResponse.json(makeSale(), { status: 201 })))

    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift()} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')
    const cashInput = screen.getByLabelText(t.sale.cashReceived)
    await user.clear(cashInput)
    await user.type(cashInput, '50')
    await user.click(screen.getByRole('button', { name: t.sale.charge }))

    await screen.findByText(t.confirmation.title)
    await user.click(screen.getByRole('button', { name: t.confirmation.newSale }))

    expect(await screen.findByText(t.sale.emptyCart)).toBeInTheDocument()
  })

  it('cancelar venta pide confirmación y solo vacía el carrito si se confirma', async () => {
    mockSearch({ refresco: [REFRESCO] })
    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift()} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')
    await user.click(screen.getByRole('button', { name: t.sale.cancelSale }))

    const dialogMessage = await screen.findByText(t.sale.confirmCancelSale)
    expect(dialogMessage).toBeInTheDocument()
    // Todavía no se canceló nada, el producto sigue en el carrito:
    expect(screen.getByText('Refresco de cola 600ml')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t.sale.confirmCancelSaleYes }))

    await waitFor(() => expect(screen.getByText(t.sale.emptyCart)).toBeInTheDocument())
  })

  it('cancelar venta y elegir "No" no vacía el carrito', async () => {
    mockSearch({ refresco: [REFRESCO] })
    const user = userEvent.setup()
    renderWithAuth(<SaleScreen shift={makeShift()} />)

    await addProductToCart(user, 'refresco', 'Refresco de cola 600ml')
    await user.click(screen.getByRole('button', { name: t.sale.cancelSale }))
    await screen.findByText(t.sale.confirmCancelSale)

    await user.click(screen.getByRole('button', { name: t.common.no }))

    expect(screen.getByText('Refresco de cola 600ml')).toBeInTheDocument()
  })
})
