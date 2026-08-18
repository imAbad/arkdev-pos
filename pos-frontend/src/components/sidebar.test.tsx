import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { makeProfile } from '@/test/fixtures'
import { server } from '@/test/server'
import { t } from '@/i18n'
import { Sidebar } from './sidebar'

const BASE = import.meta.env.VITE_API_BASE_URL
const LOW_STOCK_URL = `${BASE}/low-stock/`

function renderSidebar(profile: ReturnType<typeof makeProfile>) {
  const auth = fakeAuthValue({ profile })
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('Sidebar — link de Vender', () => {
  it('siempre está presente, sin importar el rol', () => {
    renderSidebar(makeProfile({ role: 'CAJERO', capabilities: {} }))
    expect(screen.getByRole('link', { name: t.sidebar.sell })).toBeInTheDocument()
  })
})

describe('Sidebar — link de Reportes (punto 2: mismo acceso para Supervisor que Administrador)', () => {
  it('lo muestra a un ADMINISTRADOR', () => {
    renderSidebar(makeProfile({ role: 'ADMINISTRADOR' }))
    expect(screen.getByRole('link', { name: t.reports.navLink })).toBeInTheDocument()
  })

  it('lo muestra a un CAJERO con can_authorize_exceptions (Supervisor)', () => {
    renderSidebar(makeProfile({ role: 'CAJERO', capabilities: { can_authorize_exceptions: true } }))
    expect(screen.getByRole('link', { name: t.reports.navLink })).toBeInTheDocument()
  })

  it('NO lo muestra a un CAJERO plano', () => {
    renderSidebar(makeProfile({ role: 'CAJERO', capabilities: { handles_cash: true } }))
    expect(screen.queryByRole('link', { name: t.reports.navLink })).not.toBeInTheDocument()
  })
})

describe('Sidebar — links exclusivos de ADMINISTRADOR (módulos, relacionados, usuarios, mi negocio)', () => {
  it('los muestra todos a un ADMINISTRADOR', () => {
    renderSidebar(makeProfile({ role: 'ADMINISTRADOR' }))
    expect(screen.getByRole('link', { name: t.modules.navLink })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.relatedProducts.navLink })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.users.navLink })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.branding.navLink })).toBeInTheDocument()
  })

  it('NO los muestra a un Supervisor (CAJERO con can_authorize_exceptions)', () => {
    renderSidebar(makeProfile({ role: 'CAJERO', capabilities: { can_authorize_exceptions: true } }))
    expect(screen.queryByRole('link', { name: t.modules.navLink })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.relatedProducts.navLink })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.users.navLink })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.branding.navLink })).not.toBeInTheDocument()
  })
})

describe('Sidebar — link de stock bajo (punto 7: visible a cualquier usuario, no solo admin/supervisor)', () => {
  it('lo muestra a un CAJERO plano cuando hay productos con stock bajo', async () => {
    server.use(
      http.get(LOW_STOCK_URL, () =>
        HttpResponse.json([{ product_id: 1, product_name: 'Yogurt', sku: 'YOG-1', current_stock: 1, min_stock: 5 }]),
      ),
    )
    renderSidebar(makeProfile({ role: 'CAJERO', capabilities: {} }))

    expect(await screen.findByRole('link', { name: `${t.lowStock.badgeLabel} (1)` })).toBeInTheDocument()
  })

  it('NO lo muestra cuando no hay productos con stock bajo', async () => {
    let requestResolved = false
    server.use(
      http.get(LOW_STOCK_URL, () => {
        requestResolved = true
        return HttpResponse.json([])
      }),
    )
    renderSidebar(makeProfile({ role: 'CAJERO', capabilities: {} }))

    await waitFor(() => expect(requestResolved).toBe(true))
    expect(screen.queryByRole('link', { name: /Stock bajo/ })).not.toBeInTheDocument()
  })
})
