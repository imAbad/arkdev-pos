import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { AuthContext, type AuthContextValue } from '@/features/auth/AuthProvider'
import { NavigationContext } from '@/App'
import { fakeAuthValue, fakeNavigationValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeCompanySettings, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { StoreBrandingScreen } from './StoreBrandingScreen'

const BASE = import.meta.env.VITE_API_BASE_URL

function renderScreen(authOverrides: Partial<AuthContextValue> = {}, closeBranding = vi.fn()) {
  const auth = fakeAuthValue({
    profile: makeProfile({ role: 'ADMINISTRADOR' }),
    companySettings: makeCompanySettings({ id: 7, business_name: 'Abarrotes Don Chuy', accent_color: '#1E5B94', logo: null }),
    ...authOverrides,
  })
  return render(
    <AuthContext.Provider value={auth}>
      <NavigationContext.Provider value={fakeNavigationValue({ view: 'branding', closeBranding })}>
        <StoreBrandingScreen />
      </NavigationContext.Provider>
    </AuthContext.Provider>,
  )
}

describe('StoreBrandingScreen', () => {
  it('precarga el nombre y color actuales del negocio', () => {
    renderScreen()
    expect(screen.getByLabelText(t.branding.businessName)).toHaveValue('Abarrotes Don Chuy')
    expect(screen.getByLabelText(t.branding.accentColor)).toHaveValue('#1E5B94')
  })

  it('guardar hace PATCH con nombre y color y refresca companySettings', async () => {
    let capturedBody: unknown = null
    const refreshCompanySettings = vi.fn().mockResolvedValue(undefined)
    server.use(
      http.patch(`${BASE}/company-settings/7/`, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(makeCompanySettings({ id: 7, business_name: 'Nuevo nombre', accent_color: '#C1440E' }))
      }),
    )

    const user = userEvent.setup()
    renderScreen({ refreshCompanySettings })

    const nameInput = screen.getByLabelText(t.branding.businessName)
    await user.clear(nameInput)
    await user.type(nameInput, 'Nuevo nombre')
    await user.click(screen.getByRole('button', { name: t.branding.save }))

    expect(capturedBody).toEqual({ business_name: 'Nuevo nombre', accent_color: '#1E5B94' })
    expect(await screen.findByText(t.branding.saved)).toBeInTheDocument()
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
    await user.click(screen.getByRole('button', { name: t.branding.save }))

    expect(await screen.findByText('Esta acción requiere el rol de administrador.')).toBeInTheDocument()
  })

  it('sin logo todavía, muestra el mensaje de "no hay logo" en vez de una imagen rota', () => {
    renderScreen()
    expect(screen.getByText(t.branding.logoNone)).toBeInTheDocument()
  })

  it('subir un logo hace PATCH multipart y refresca companySettings', async () => {
    let receivedContentType: string | null = null
    const refreshCompanySettings = vi.fn().mockResolvedValue(undefined)
    server.use(
      http.patch(`${BASE}/company-settings/7/`, ({ request }) => {
        receivedContentType = request.headers.get('content-type')
        return HttpResponse.json(makeCompanySettings({ id: 7, logo: 'http://localhost:8000/media/logo.png' }))
      }),
    )

    const user = userEvent.setup()
    renderScreen({ refreshCompanySettings })

    const file = new File(['fake-image-bytes'], 'logo.png', { type: 'image/png' })
    const fileInput = document.querySelector('#logo-file') as HTMLInputElement
    await user.upload(fileInput, file)
    await user.click(screen.getByRole('button', { name: t.branding.uploadLogo }))

    expect(await screen.findByText(t.branding.logoUploaded)).toBeInTheDocument()
    expect(receivedContentType).toMatch(/multipart\/form-data/)
    expect(refreshCompanySettings).toHaveBeenCalledTimes(1)
  })

  it('"Volver a vender" llama a closeBranding', async () => {
    const closeBranding = vi.fn()
    const user = userEvent.setup()
    renderScreen({}, closeBranding)

    await user.click(screen.getByRole('button', { name: t.branding.back }))
    expect(closeBranding).toHaveBeenCalledTimes(1)
  })
})
