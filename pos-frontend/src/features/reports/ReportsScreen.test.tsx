import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import { render } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { NavigationContext } from '@/App'
import { fakeAuthValue, fakeNavigationValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeBranch, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { ReportsScreen } from './ReportsScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const BRANCHES_URL = `${BASE}/branches/`
const SALES_BY_PRODUCT_URL = `${BASE}/reports/sales-by-product/`
const INVENTORY_VALUATION_URL = `${BASE}/reports/inventory-valuation/`
const NEAR_EXPIRY_URL = `${BASE}/reports/near-expiry-stock/`

function renderReportsScreen(closeReports = vi.fn()) {
  const auth = fakeAuthValue({ profile: makeProfile({ role: 'ADMINISTRADOR' }) })
  return render(
    <AuthContext.Provider value={auth}>
      <NavigationContext.Provider value={fakeNavigationValue({ view: 'reports', closeReports })}>
        <ReportsScreen />
      </NavigationContext.Provider>
    </AuthContext.Provider>,
  )
}

describe('ReportsScreen', () => {
  it('carga y muestra el reporte de ventas por producto por default', async () => {
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () =>
        HttpResponse.json([
          { product_id: 1, product_name: 'Arroz superextra 1kg', category_name: 'Básicos', quantity_sold: '5.000', revenue: '120.00', tax: '0.00' },
        ]),
      ),
    )

    renderReportsScreen()

    expect(await screen.findByText('Arroz superextra 1kg')).toBeInTheDocument()
    expect(screen.getByText('$120.00')).toBeInTheDocument()
  })

  it('muestra el mensaje de "sin datos" cuando el reporte viene vacío', async () => {
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () => HttpResponse.json([])),
    )

    renderReportsScreen()

    expect(await screen.findByText(t.reports.empty)).toBeInTheDocument()
  })

  it('cambiar a "Valuación de inventario" oculta los filtros de fecha y consulta ese reporte', async () => {
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () => HttpResponse.json([])),
      http.get(INVENTORY_VALUATION_URL, () =>
        HttpResponse.json([
          { product_id: 1, product_name: 'Yogurt natural 1L', category_name: 'Básicos', quantity: 50, valuation: '1300.00' },
        ]),
      ),
    )

    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)

    await user.click(screen.getByRole('button', { name: t.reports.tabInventoryValuation }))

    expect(await screen.findByText('Yogurt natural 1L')).toBeInTheDocument()
    expect(screen.getByText('Total: $1,300.00')).toBeInTheDocument()
    expect(screen.queryByLabelText(t.reports.dateFrom)).not.toBeInTheDocument()
  })

  it('el filtro de sucursal lista las sucursales del tenant', async () => {
    server.use(
      http.get(BRANCHES_URL, () =>
        HttpResponse.json({
          count: 2, next: null, previous: null,
          results: [makeBranch({ id: 1, name: 'Sucursal Centro' }), makeBranch({ id: 2, name: 'Sucursal Norte' })],
        }),
      ),
      http.get(SALES_BY_PRODUCT_URL, () => HttpResponse.json([])),
    )

    renderReportsScreen()

    await screen.findByText(t.reports.empty)
    expect(screen.getByRole('option', { name: 'Sucursal Centro' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Sucursal Norte' })).toBeInTheDocument()
  })

  it('"Volver a vender" llama a closeReports', async () => {
    const closeReports = vi.fn()
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () => HttpResponse.json([])),
    )

    const user = userEvent.setup()
    renderReportsScreen(closeReports)
    await screen.findByText(t.reports.empty)

    await user.click(screen.getByRole('button', { name: t.reports.back }))
    expect(closeReports).toHaveBeenCalledTimes(1)
  })

  it('punto 4: "Próximos a caducar" usa un filtro de días, no de fechas, y lo manda como query param', async () => {
    let capturedDays: string | null = null
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () => HttpResponse.json([])),
      http.get(NEAR_EXPIRY_URL, ({ request }) => {
        capturedDays = new URL(request.url).searchParams.get('days')
        return HttpResponse.json([
          { batch_id: 1, batch_number: 'L-1', product_id: 1, product_name: 'Yogurt natural 1L', branch_id: 1, branch_name: 'Centro', expiration_date: '2026-08-25', days_to_expire: 3, quantity: 4, valuation: '20.00' },
        ])
      }),
    )

    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)

    await user.click(screen.getByRole('button', { name: t.reports.tabNearExpiry }))

    expect(await screen.findByText('Yogurt natural 1L')).toBeInTheDocument()
    expect(screen.queryByLabelText(t.reports.dateFrom)).not.toBeInTheDocument()
    expect(screen.getByLabelText(t.reports.daysWindow)).toBeInTheDocument()
    expect(capturedDays).toBe('7')
  })

  it('si el backend rechaza (403, sin rol de administrador), muestra el mensaje humano y no rompe la pantalla', async () => {
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () =>
        HttpResponse.json({ code: 'PermissionDenied', detail: 'Esta acción requiere el rol de administrador.' }, { status: 403 }),
      ),
    )

    renderReportsScreen()

    expect(await screen.findByText('Esta acción requiere el rol de administrador.')).toBeInTheDocument()
  })
})
