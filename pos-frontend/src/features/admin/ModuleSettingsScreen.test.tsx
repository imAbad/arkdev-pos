import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { AuthContext, type AuthContextValue } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeCompanySettings, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { ModuleSettingsScreen } from './ModuleSettingsScreen'

const BASE = import.meta.env.VITE_API_BASE_URL

function renderScreen(authOverrides: Partial<AuthContextValue> = {}) {
  const auth = fakeAuthValue({
    profile: makeProfile({ role: 'ADMINISTRADOR' }),
    companySettings: makeCompanySettings({ id: 7, enabled_modules: { cfdi: false, multiple_branches: false } }),
    ...authOverrides,
  })
  return render(
    <AuthContext.Provider value={auth}>
      <ModuleSettingsScreen />
    </AuthContext.Provider>,
  )
}

describe('ModuleSettingsScreen', () => {
  it('muestra los dos módulos reales (cfdi, multiple_branches) apagados por default', () => {
    renderScreen()
    expect(screen.getByText(t.modules.cfdiName)).toBeInTheDocument()
    expect(screen.getByText(t.modules.multipleBranchesName)).toBeInTheDocument()
    const switches = screen.getAllByRole('switch')
    expect(switches).toHaveLength(2)
    switches.forEach((sw) => expect(sw).toHaveAttribute('aria-checked', 'false'))
  })

  it('activar un módulo hace PATCH con el resto de las claves intactas y refresca companySettings', async () => {
    let capturedBody: unknown = null
    const refreshCompanySettings = vi.fn().mockResolvedValue(undefined)
    server.use(
      http.patch(`${BASE}/company-settings/7/`, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(makeCompanySettings({ id: 7, enabled_modules: { cfdi: true, multiple_branches: false } }))
      }),
    )

    const user = userEvent.setup()
    renderScreen({ refreshCompanySettings })

    await user.click(screen.getByRole('switch', { name: t.modules.cfdiName }))

    expect(capturedBody).toEqual({ enabled_modules: { cfdi: true, multiple_branches: false } })
    expect(await screen.findByText(t.modules.saved)).toBeInTheDocument()
    expect(refreshCompanySettings).toHaveBeenCalledTimes(1)
  })

  it('si el backend rechaza (403), muestra el mensaje humano sin romper la pantalla', async () => {
    server.use(
      http.patch(`${BASE}/company-settings/7/`, () =>
        HttpResponse.json({ detail: 'Esta acción requiere el rol de administrador.' }, { status: 403 }),
      ),
    )

    const user = userEvent.setup()
    renderScreen()

    await user.click(screen.getByRole('switch', { name: t.modules.cfdiName }))

    expect(await screen.findByText('Esta acción requiere el rol de administrador.')).toBeInTheDocument()
  })
})
