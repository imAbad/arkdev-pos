import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { AuthContext } from '@/features/auth/AuthProvider'
import { NavigationContext } from '@/App'
import { fakeAuthValue, fakeNavigationValue } from '@/test/test-utils'
import { makeProfile } from '@/test/fixtures'
import { server } from '@/test/server'
import { t } from '@/i18n'
import { AppHeader } from './app-header'

const BASE = import.meta.env.VITE_API_BASE_URL
const LOW_STOCK_URL = `${BASE}/low-stock/`

function renderHeader(profile: ReturnType<typeof makeProfile>) {
  const auth = fakeAuthValue({ profile })
  return render(
    <AuthContext.Provider value={auth}>
      <NavigationContext.Provider value={fakeNavigationValue()}>
        <AppHeader />
      </NavigationContext.Provider>
    </AuthContext.Provider>,
  )
}

describe('AppHeader — link de Reportes (punto 2: mismo acceso para Supervisor que Administrador)', () => {
  it('lo muestra a un ADMINISTRADOR', () => {
    renderHeader(makeProfile({ role: 'ADMINISTRADOR' }))
    expect(screen.getByRole('button', { name: t.reports.navLink })).toBeInTheDocument()
  })

  it('lo muestra a un CAJERO con can_authorize_exceptions (Supervisor)', () => {
    renderHeader(makeProfile({ role: 'CAJERO', capabilities: { can_authorize_exceptions: true } }))
    expect(screen.getByRole('button', { name: t.reports.navLink })).toBeInTheDocument()
  })

  it('NO lo muestra a un CAJERO plano', () => {
    renderHeader(makeProfile({ role: 'CAJERO', capabilities: { handles_cash: true } }))
    expect(screen.queryByRole('button', { name: t.reports.navLink })).not.toBeInTheDocument()
  })
})

describe('AppHeader — link de Relacionados (punto 5, exclusivo de ADMINISTRADOR)', () => {
  it('lo muestra a un ADMINISTRADOR', () => {
    renderHeader(makeProfile({ role: 'ADMINISTRADOR' }))
    expect(screen.getByRole('button', { name: t.relatedProducts.navLink })).toBeInTheDocument()
  })

  it('NO lo muestra a un Supervisor (CAJERO con can_authorize_exceptions)', () => {
    renderHeader(makeProfile({ role: 'CAJERO', capabilities: { can_authorize_exceptions: true } }))
    expect(screen.queryByRole('button', { name: t.relatedProducts.navLink })).not.toBeInTheDocument()
  })
})

describe('AppHeader — link de Usuarios (punto 9, exclusivo de ADMINISTRADOR sin excepción)', () => {
  it('lo muestra a un ADMINISTRADOR', () => {
    renderHeader(makeProfile({ role: 'ADMINISTRADOR' }))
    expect(screen.getByRole('button', { name: t.users.navLink })).toBeInTheDocument()
  })

  it('NO lo muestra a un Supervisor (CAJERO con can_authorize_exceptions)', () => {
    renderHeader(makeProfile({ role: 'CAJERO', capabilities: { can_authorize_exceptions: true } }))
    expect(screen.queryByRole('button', { name: t.users.navLink })).not.toBeInTheDocument()
  })
})

describe('AppHeader — link de Mi negocio (punto 12, exclusivo de ADMINISTRADOR)', () => {
  it('lo muestra a un ADMINISTRADOR', () => {
    renderHeader(makeProfile({ role: 'ADMINISTRADOR' }))
    expect(screen.getByRole('button', { name: t.branding.navLink })).toBeInTheDocument()
  })

  it('NO lo muestra a un Supervisor (CAJERO con can_authorize_exceptions)', () => {
    renderHeader(makeProfile({ role: 'CAJERO', capabilities: { can_authorize_exceptions: true } }))
    expect(screen.queryByRole('button', { name: t.branding.navLink })).not.toBeInTheDocument()
  })
})

describe('AppHeader — badge de stock bajo (punto 7: visible a cualquier usuario, no solo admin/supervisor)', () => {
  it('lo muestra a un CAJERO plano cuando hay productos con stock bajo', async () => {
    server.use(
      http.get(LOW_STOCK_URL, () =>
        HttpResponse.json([{ product_id: 1, product_name: 'Yogurt', sku: 'YOG-1', current_stock: 1, min_stock: 5 }]),
      ),
    )
    renderHeader(makeProfile({ role: 'CAJERO', capabilities: {} }))

    expect(await screen.findByRole('button', { name: `${t.lowStock.badgeLabel} (1)` })).toBeInTheDocument()
  })

  it('NO lo muestra cuando no hay productos con stock bajo', async () => {
    let requestResolved = false
    server.use(
      http.get(LOW_STOCK_URL, () => {
        requestResolved = true
        return HttpResponse.json([])
      }),
    )
    renderHeader(makeProfile({ role: 'CAJERO', capabilities: {} }))

    await waitFor(() => expect(requestResolved).toBe(true))
    expect(screen.queryByRole('button', { name: /Stock bajo/ })).not.toBeInTheDocument()
  })
})
