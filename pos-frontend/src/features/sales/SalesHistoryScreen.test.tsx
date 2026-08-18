import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeProfile, makeSale } from '@/test/fixtures'
import { t } from '@/i18n'
import { SalesHistoryScreen } from './SalesHistoryScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const SALES_URL = `${BASE}/sales/`

const SALE = makeSale({
  id: 42,
  cashier_email: 'cajero@donchuy.test',
  total: '34.00',
  status: 'COMPLETED',
  details: [
    { id: 1, product: 1, product_name: 'Yogurt natural 1L', product_unit_type: 'PIEZA', batch: null, quantity: '1.000', unit_price: '34.00', tax_rate_applied: '0.00', tax_amount: '0.00', subtotal: '34.00' },
  ],
  payments: [{ id: 1, method: 'CASH', amount: '34.00', reference: '' }],
})

function renderScreen() {
  const auth = fakeAuthValue({ profile: makeProfile({ role: 'ADMINISTRADOR' }) })
  return render(
    <AuthContext.Provider value={auth}>
      <SalesHistoryScreen />
    </AuthContext.Provider>,
  )
}

describe('SalesHistoryScreen', () => {
  it('lista las ventas del rango con cajero, total y estado', async () => {
    server.use(http.get(SALES_URL, () => HttpResponse.json({ count: 1, next: null, previous: null, results: [SALE] })))
    renderScreen()

    expect(await screen.findByText('cajero@donchuy.test')).toBeInTheDocument()
    expect(screen.getByText('$34.00')).toBeInTheDocument()
    expect(screen.getByText(t.salesHistory.statusCompleted)).toBeInTheDocument()
  })

  it('muestra el mensaje de "sin ventas" cuando el rango viene vacío', async () => {
    server.use(http.get(SALES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })))
    renderScreen()

    expect(await screen.findByText(t.salesHistory.empty)).toBeInTheDocument()
  })

  it('clic en una fila abre el ticket de esa venta (con cancelar ya disponible)', async () => {
    server.use(http.get(SALES_URL, () => HttpResponse.json({ count: 1, next: null, previous: null, results: [SALE] })))
    const user = userEvent.setup()
    renderScreen()

    await screen.findByText('cajero@donchuy.test')
    await user.click(screen.getByText('cajero@donchuy.test'))

    expect(await screen.findByText('Yogurt natural 1L')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.ticket.cancelSale })).toBeInTheDocument()
  })

  it('"Volver" desde el ticket regresa a la lista', async () => {
    server.use(http.get(SALES_URL, () => HttpResponse.json({ count: 1, next: null, previous: null, results: [SALE] })))
    const user = userEvent.setup()
    renderScreen()

    await screen.findByText('cajero@donchuy.test')
    await user.click(screen.getByText('cajero@donchuy.test'))
    await screen.findByRole('button', { name: t.ticket.back })

    await user.click(screen.getByRole('button', { name: t.ticket.back }))

    expect(await screen.findByText('cajero@donchuy.test')).toBeInTheDocument()
  })
})
