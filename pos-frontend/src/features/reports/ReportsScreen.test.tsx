import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import { render } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeBranch, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { ReportsScreen } from './ReportsScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const BRANCHES_URL = `${BASE}/branches/`
const SALES_BY_PRODUCT_URL = `${BASE}/reports/sales-by-product/`
const INVENTORY_VALUATION_URL = `${BASE}/reports/inventory-valuation/`
const NEAR_EXPIRY_URL = `${BASE}/reports/near-expiry-stock/`
const CASH_SHIFT_CLOSURES_URL = `${BASE}/reports/cash-shift-closures/`
const CASH_SHIFT_DETAIL_URL = `${BASE}/reports/cash-shift-detail/`
const INVENTORY_ADJUSTMENTS_URL = `${BASE}/reports/inventory-adjustments/`

// jsdom no implementa createObjectURL/revokeObjectURL — se agregan al
// URL real (no se reemplaza el global: axios usa `new URL(...)` para
// resolver la request, reemplazar el constructor completo rompe eso)
// para poder probar el flujo real de descarga (punto 11).
URL.createObjectURL = vi.fn(() => 'blob:mock')
URL.revokeObjectURL = vi.fn()

function renderReportsScreen() {
  const auth = fakeAuthValue({ profile: makeProfile({ role: 'ADMINISTRADOR' }) })
  return render(
    <AuthContext.Provider value={auth}>
      <ReportsScreen />
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

describe('ReportsScreen — Cierre de turno detallado (drill-down de un turno)', () => {
  function mockClosuresList() {
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () => HttpResponse.json([])),
      http.get(CASH_SHIFT_CLOSURES_URL, () =>
        HttpResponse.json([
          {
            id: 42, branch_name: 'Centro', register_name: 'Caja 1', user_email: 'cajero@donchuy.test',
            opened_at: '2026-08-18T14:00:00Z', closed_at: '2026-08-18T20:00:00Z',
            opening_balance: '500.00', expected_closing_balance: '650.00', actual_closing_balance: '650.00',
            cash_difference: '0.00', expected_voucher_total: '0.00', actual_voucher_total: '0.00', voucher_difference: '0.00',
          },
        ]),
      ),
    )
  }

  function mockShiftDetail() {
    server.use(
      http.get(CASH_SHIFT_DETAIL_URL, () =>
        HttpResponse.json({
          shift_id: 42, branch_name: 'Centro', register_name: 'Caja 1', user_email: 'cajero@donchuy.test',
          opened_at: '2026-08-18T14:00:00Z', closed_at: '2026-08-18T20:00:00Z',
          opening_balance: '500.00', expected_closing_balance: '650.00', actual_closing_balance: '650.00',
          cash_difference: '0.00', expected_voucher_total: '0.00', actual_voucher_total: '0.00', voucher_difference: '0.00',
          sales_count: 2, sales_total: '150.00',
          payments_by_method: [{ method: 'CASH', method_label: 'Efectivo', total: '150.00' }],
          credit_payments: [{ id: 1, client_name: 'Cliente Fiel', amount: '80.00', created_at: '2026-08-18T16:00:00Z' }],
          credit_payments_total: '80.00',
        }),
      ),
    )
  }

  it('lista los turnos cerrados con un botón de "Ver detalle" por fila', async () => {
    mockClosuresList()
    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)

    await user.click(screen.getByRole('button', { name: t.reports.tabShiftDetail }))

    expect(await screen.findByText('cajero@donchuy.test')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.reports.shiftDetailViewDetail })).toBeInTheDocument()
  })

  it('"Ver detalle" carga y muestra el desglose completo del turno', async () => {
    mockClosuresList()
    mockShiftDetail()
    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)
    await user.click(screen.getByRole('button', { name: t.reports.tabShiftDetail }))
    await screen.findByRole('button', { name: t.reports.shiftDetailViewDetail })

    await user.click(screen.getByRole('button', { name: t.reports.shiftDetailViewDetail }))

    expect(await screen.findByText(t.reports.shiftDetailSummaryTitle)).toBeInTheDocument()
    expect(screen.getByText('Efectivo')).toBeInTheDocument()
    expect(screen.getByText('Cliente Fiel')).toBeInTheDocument()
    expect(screen.getByText('$80.00')).toBeInTheDocument()
  })

  it('"Volver a la lista" regresa al listado de turnos', async () => {
    mockClosuresList()
    mockShiftDetail()
    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)
    await user.click(screen.getByRole('button', { name: t.reports.tabShiftDetail }))
    await user.click(await screen.findByRole('button', { name: t.reports.shiftDetailViewDetail }))
    await screen.findByText(t.reports.shiftDetailSummaryTitle)

    await user.click(screen.getByRole('button', { name: t.reports.shiftDetailBackToList }))

    expect(screen.queryByText(t.reports.shiftDetailSummaryTitle)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.reports.shiftDetailViewDetail })).toBeInTheDocument()
  })

  it('cuando no hay abonos a crédito en el turno, muestra el mensaje explícito en vez de una tabla vacía', async () => {
    mockClosuresList()
    server.use(
      http.get(CASH_SHIFT_DETAIL_URL, () =>
        HttpResponse.json({
          shift_id: 42, branch_name: 'Centro', register_name: 'Caja 1', user_email: 'cajero@donchuy.test',
          opened_at: '2026-08-18T14:00:00Z', closed_at: '2026-08-18T20:00:00Z',
          opening_balance: '500.00', expected_closing_balance: '500.00', actual_closing_balance: '500.00',
          cash_difference: '0.00', expected_voucher_total: '0.00', actual_voucher_total: '0.00', voucher_difference: '0.00',
          sales_count: 0, sales_total: '0.00', payments_by_method: [], credit_payments: [], credit_payments_total: '0.00',
        }),
      ),
    )
    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)
    await user.click(screen.getByRole('button', { name: t.reports.tabShiftDetail }))
    await user.click(await screen.findByRole('button', { name: t.reports.shiftDetailViewDetail }))

    expect(await screen.findByText(t.reports.shiftDetailNoCreditPayments)).toBeInTheDocument()
  })
})

describe('ReportsScreen — Ajustes de inventario (punto 4: motivo visible, no enterrado en la BD)', () => {
  it('lista los ajustes con motivo, cantidad y quién', async () => {
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () => HttpResponse.json([])),
      http.get(INVENTORY_ADJUSTMENTS_URL, () =>
        HttpResponse.json([
          {
            id: 1, product_name: 'Yogurt natural 1L', batch_number: 'L-1', branch_name: 'Centro',
            quantity_delta: -3, quantity_before: 20, quantity_after: 17,
            reason_label: 'Merma/rotura', reason_detail: '', user_email: 'admin@donchuy.test',
            created_at: '2026-08-18T12:00:00Z',
          },
        ]),
      ),
    )
    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)

    await user.click(screen.getByRole('button', { name: t.reports.tabInventoryAdjustments }))

    expect(await screen.findByText('Yogurt natural 1L')).toBeInTheDocument()
    expect(screen.getByText('-3')).toBeInTheDocument()
    expect(screen.getByText('Merma/rotura')).toBeInTheDocument()
    expect(screen.getByText('admin@donchuy.test')).toBeInTheDocument()
  })
})

describe('ReportsScreen — exportar a Excel (punto 11, solo los 4 reportes ya existentes)', () => {
  it('el botón de exportar dispara la descarga con export=xlsx', async () => {
    let capturedParams: URLSearchParams | null = null
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, ({ request }) => {
        const url = new URL(request.url)
        if (url.searchParams.get('export') === 'xlsx') {
          capturedParams = url.searchParams
          return HttpResponse.arrayBuffer(new ArrayBuffer(8), {
            headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
          })
        }
        return HttpResponse.json([])
      }),
    )

    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)

    await user.click(screen.getByRole('button', { name: t.reports.exportToExcel }))

    expect(await screen.findByRole('button', { name: t.reports.exportToExcel })).toBeInTheDocument()
    expect(capturedParams).not.toBeNull()
    expect(capturedParams!.get('group_by')).toBe('product')
  })

  it('no muestra el botón de exportar en la pestaña "Próximos a caducar" (no es uno de los 4 reportes existentes)', async () => {
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, () => HttpResponse.json([])),
      http.get(NEAR_EXPIRY_URL, () => HttpResponse.json([])),
    )

    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)

    await user.click(screen.getByRole('button', { name: t.reports.tabNearExpiry }))

    expect(screen.queryByRole('button', { name: t.reports.exportToExcel })).not.toBeInTheDocument()
  })

  it('muestra un mensaje legible si la exportación falla', async () => {
    server.use(
      http.get(BRANCHES_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.get(SALES_BY_PRODUCT_URL, ({ request }) => {
        const url = new URL(request.url)
        if (url.searchParams.get('export') === 'xlsx') {
          return HttpResponse.json({ detail: 'Esta acción requiere el rol de administrador.' }, { status: 403 })
        }
        return HttpResponse.json([])
      }),
    )

    const user = userEvent.setup()
    renderReportsScreen()
    await screen.findByText(t.reports.empty)

    await user.click(screen.getByRole('button', { name: t.reports.exportToExcel }))

    expect(await screen.findByText(t.reports.exportErrorGeneric)).toBeInTheDocument()
  })
})
