import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen, within } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { NavigationContext } from '@/App'
import { fakeAuthValue, fakeNavigationValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeBranch, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { UserManagementScreen } from './UserManagementScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const USERS_URL = `${BASE}/user-profiles/`
const BRANCHES_URL = `${BASE}/branches/`

const CENTRO = makeBranch({ id: 1, name: 'Centro' })

const ADMIN_PROFILE = { id: 1, email: 'admin@donchuy.test', is_active: true, branch: 1, role: 'ADMINISTRADOR' as const, capabilities: {}, company: 1 }
const CAJERO_PROFILE = { id: 2, email: 'cajero@donchuy.test', is_active: true, branch: 1, role: 'CAJERO' as const, capabilities: { handles_cash: true }, company: 1 }
const INACTIVE_PROFILE = { id: 3, email: 'exempleado@donchuy.test', is_active: false, branch: 1, role: 'CAJERO' as const, capabilities: {}, company: 1 }

function mockLists(users = [ADMIN_PROFILE, CAJERO_PROFILE]) {
  server.use(
    http.get(USERS_URL, () => HttpResponse.json({ count: users.length, next: null, previous: null, results: users })),
    http.get(BRANCHES_URL, () => HttpResponse.json({ count: 1, next: null, previous: null, results: [CENTRO] })),
  )
}

function renderScreen() {
  const auth = fakeAuthValue({ profile: makeProfile({ role: 'ADMINISTRADOR' }) })
  return render(
    <AuthContext.Provider value={auth}>
      <NavigationContext.Provider value={fakeNavigationValue({ view: 'users', closeUsers: vi.fn() })}>
        <UserManagementScreen />
      </NavigationContext.Provider>
    </AuthContext.Provider>,
  )
}

describe('UserManagementScreen', () => {
  it('lista los usuarios del tenant con su rol, sucursal y estado', async () => {
    mockLists()
    renderScreen()

    const adminEmail = await screen.findByText('admin@donchuy.test')
    const cajeroEmail = screen.getByText('cajero@donchuy.test')

    const adminRow = adminEmail.closest('tr')!
    const cajeroRow = cajeroEmail.closest('tr')!
    expect(within(adminRow).getByText('Centro')).toBeInTheDocument()
    expect(within(cajeroRow).getByText('Centro')).toBeInTheDocument()
    expect(within(adminRow).getByText(t.users.statusActive)).toBeInTheDocument()
    expect(within(cajeroRow).getByText(t.users.statusActive)).toBeInTheDocument()
  })

  it('crea un usuario nuevo con el formulario', async () => {
    mockLists()
    let createdBody: unknown = null
    server.use(
      http.post(USERS_URL, async ({ request }) => {
        createdBody = await request.json()
        return HttpResponse.json(
          { id: 99, email: 'nuevo@donchuy.test', is_active: true, branch: 1, role: 'CAJERO', capabilities: { handles_cash: true }, company: 1 },
          { status: 201 },
        )
      }),
    )
    renderScreen()
    await screen.findByText('admin@donchuy.test')

    await userEvent.type(screen.getByLabelText(t.users.email), 'nuevo@donchuy.test')
    await userEvent.type(screen.getByLabelText(t.users.password), 'ClaveSegura2026!')
    await userEvent.selectOptions(screen.getByLabelText(t.users.branch), '1')
    await userEvent.click(screen.getByLabelText(t.users.handlesCash))
    await userEvent.click(screen.getByRole('button', { name: t.users.create }))

    expect(await screen.findByText(t.users.createdNotice)).toBeInTheDocument()
    expect(createdBody).toMatchObject({ email: 'nuevo@donchuy.test', branch: 1, role: 'CAJERO' })
  })

  it('muestra un error legible cuando la creación falla (ej. correo duplicado)', async () => {
    mockLists()
    server.use(
      http.post(USERS_URL, () => HttpResponse.json({ detail: 'Ya existe un usuario con este correo.' }, { status: 400 })),
    )
    renderScreen()
    await screen.findByText('admin@donchuy.test')

    await userEvent.type(screen.getByLabelText(t.users.email), 'admin@donchuy.test')
    await userEvent.type(screen.getByLabelText(t.users.password), 'ClaveSegura2026!')
    await userEvent.selectOptions(screen.getByLabelText(t.users.branch), '1')
    await userEvent.click(screen.getByRole('button', { name: t.users.create }))

    expect(await screen.findByText('Ya existe un usuario con este correo.')).toBeInTheDocument()
  })

  it('desactiva a un usuario activo', async () => {
    mockLists()
    server.use(
      http.post(`${USERS_URL}2/deactivate/`, () =>
        HttpResponse.json({ ...CAJERO_PROFILE, is_active: false }),
      ),
    )
    renderScreen()
    await screen.findByText('cajero@donchuy.test')

    const row = screen.getByText('cajero@donchuy.test').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: t.users.deactivate }))

    expect(await within(row).findByText(t.users.statusInactive)).toBeInTheDocument()
  })

  it('muestra el error de la salvaguarda cuando se intenta desactivar al último admin', async () => {
    mockLists()
    server.use(
      http.post(`${USERS_URL}1/deactivate/`, () =>
        HttpResponse.json({ detail: 'No puedes desactivar al último administrador activo del negocio.' }, { status: 400 }),
      ),
    )
    renderScreen()
    await screen.findByText('admin@donchuy.test')

    const row = screen.getByText('admin@donchuy.test').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: t.users.deactivate }))

    expect(await screen.findByText('No puedes desactivar al último administrador activo del negocio.')).toBeInTheDocument()
  })

  it('reactiva a un usuario inactivo', async () => {
    mockLists([ADMIN_PROFILE, INACTIVE_PROFILE])
    server.use(
      http.post(`${USERS_URL}3/reactivate/`, () =>
        HttpResponse.json({ ...INACTIVE_PROFILE, is_active: true }),
      ),
    )
    renderScreen()
    await screen.findByText('exempleado@donchuy.test')

    const row = screen.getByText('exempleado@donchuy.test').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: t.users.reactivate }))

    expect(await within(row).findByText(t.users.statusActive)).toBeInTheDocument()
  })
})
