import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { NavigationContext } from '@/App'
import { fakeAuthValue } from '@/test/test-utils'
import { makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { AppHeader } from './app-header'

function renderHeader(profile: ReturnType<typeof makeProfile>) {
  const auth = fakeAuthValue({ profile })
  return render(
    <AuthContext.Provider value={auth}>
      <NavigationContext.Provider value={{ view: 'main', openReports: vi.fn(), closeReports: vi.fn(), openModules: vi.fn(), closeModules: vi.fn() }}>
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
