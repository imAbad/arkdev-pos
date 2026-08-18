import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { LowStockScreen } from './LowStockScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const LOW_STOCK_URL = `${BASE}/low-stock/`

function renderScreen() {
  const auth = fakeAuthValue({ profile: makeProfile({ role: 'CAJERO', capabilities: { handles_cash: true } }) })
  return render(
    <AuthContext.Provider value={auth}>
      <LowStockScreen />
    </AuthContext.Provider>,
  )
}

describe('LowStockScreen', () => {
  it('muestra la lista completa de productos con stock bajo', async () => {
    server.use(
      http.get(LOW_STOCK_URL, () =>
        HttpResponse.json([
          { product_id: 1, product_name: 'Yogurt natural 1L', sku: 'YOG-1', current_stock: 2, min_stock: 10 },
        ]),
      ),
    )
    renderScreen()

    expect(await screen.findByText('Yogurt natural 1L')).toBeInTheDocument()
    expect(screen.getByText('YOG-1')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
  })

  it('muestra un mensaje claro cuando no hay nada con stock bajo', async () => {
    server.use(http.get(LOW_STOCK_URL, () => HttpResponse.json([])))
    renderScreen()

    expect(await screen.findByText(t.lowStock.empty)).toBeInTheDocument()
  })

  it('muestra un error legible (no crudo) cuando la carga falla', async () => {
    server.use(http.get(LOW_STOCK_URL, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    renderScreen()

    expect(await screen.findByRole('alert')).toHaveTextContent(t.common.errorServer)
  })
})
