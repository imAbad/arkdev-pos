import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthContext } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { makeBranch, makeCompanySettings, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { AppHeader } from './app-header'

/** Punto 13: la navegación entre pantallas se movió al Sidebar (ver
 * sidebar.test.tsx) — AppHeader ya solo es identidad del tenant +
 * cerrar sesión. */
describe('AppHeader', () => {
  it('muestra el nombre del negocio y la sucursal', () => {
    const auth = fakeAuthValue({
      companySettings: makeCompanySettings({ business_name: 'Abarrotes Don Chuy' }),
      branch: makeBranch({ name: 'Centro' }),
    })
    render(
      <AuthContext.Provider value={auth}>
        <AppHeader />
      </AuthContext.Provider>,
    )
    expect(screen.getByText('Abarrotes Don Chuy')).toBeInTheDocument()
    expect(screen.getByText('Centro')).toBeInTheDocument()
  })

  it('usa el nombre genérico de la app si el tenant no configuró un business_name', () => {
    const auth = fakeAuthValue({ companySettings: makeCompanySettings({ business_name: '' }) })
    render(
      <AuthContext.Provider value={auth}>
        <AppHeader />
      </AuthContext.Provider>,
    )
    expect(screen.getByText(t.common.appName)).toBeInTheDocument()
  })

  it('cerrar sesión llama a logout', async () => {
    const logout = vi.fn()
    const auth = fakeAuthValue({ profile: makeProfile(), logout })
    const user = userEvent.setup()
    render(
      <AuthContext.Provider value={auth}>
        <AppHeader />
      </AuthContext.Provider>,
    )

    await user.click(screen.getByRole('button', { name: t.common.logout }))
    expect(logout).toHaveBeenCalledTimes(1)
  })
})
