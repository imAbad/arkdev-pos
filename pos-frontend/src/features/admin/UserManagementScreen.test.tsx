import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeBranch, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import type { UserProfile } from '@/types/api'
import { UserManagementScreen } from './UserManagementScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const USERS_URL = `${BASE}/user-profiles/`
const BRANCHES_URL = `${BASE}/branches/`

const CENTRO = makeBranch({ id: 1, name: 'Centro' })

const ADMIN_PROFILE = { id: 1, email: 'admin@donchuy.test', username: 'admin1', is_active: true, branch: 1, role: 'ADMINISTRADOR' as const, capabilities: {}, date_of_birth: '1980-01-01', company: 1 }
const CAJERO_PROFILE = { id: 2, email: 'cajero@donchuy.test', username: 'cajero1', is_active: true, branch: 1, role: 'CAJERO' as const, capabilities: { handles_cash: true }, date_of_birth: '1998-06-20', company: 1 }
const INACTIVE_PROFILE = { id: 3, email: 'exempleado@donchuy.test', username: null, is_active: false, branch: 1, role: 'CAJERO' as const, capabilities: {}, date_of_birth: null, company: 1 }

function mockLists(users: UserProfile[] = [ADMIN_PROFILE, CAJERO_PROFILE]) {
  server.use(
    http.get(USERS_URL, () => HttpResponse.json({ count: users.length, next: null, previous: null, results: users })),
    http.get(BRANCHES_URL, () => HttpResponse.json({ count: 1, next: null, previous: null, results: [CENTRO] })),
  )
}

function renderScreen() {
  const auth = fakeAuthValue({ profile: makeProfile({ role: 'ADMINISTRADOR' }) })
  return render(
    <AuthContext.Provider value={auth}>
      <UserManagementScreen />
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

  it('la fila de un usuario sin correo muestra un guion, no vacío ni error', async () => {
    mockLists([ADMIN_PROFILE, { ...CAJERO_PROFILE, email: null }])
    renderScreen()

    const cajeroRow = (await screen.findByText('cajero1')).closest('tr')!
    expect(within(cajeroRow).getByText('—')).toBeInTheDocument()
  })

  it('crea un usuario nuevo con el formulario (username + email opcional)', async () => {
    mockLists()
    let createdBody: unknown = null
    server.use(
      http.post(USERS_URL, async ({ request }) => {
        createdBody = await request.json()
        return HttpResponse.json(
          {
            id: 99, email: 'nuevo@donchuy.test', username: 'nuevo_cajero', is_active: true, branch: 1,
            role: 'CAJERO', capabilities: { handles_cash: true }, date_of_birth: '1998-06-20', company: 1,
          },
          { status: 201 },
        )
      }),
    )
    renderScreen()
    await screen.findByText('admin@donchuy.test')

    await userEvent.type(screen.getByLabelText(t.users.username), 'nuevo_cajero')
    await userEvent.type(screen.getByLabelText(t.users.password), 'ClaveSegura2026!')
    await userEvent.type(screen.getByLabelText(t.users.email), 'nuevo@donchuy.test')
    fireEvent.change(screen.getByLabelText(t.users.dateOfBirth), { target: { value: '1998-06-20' } })
    await userEvent.selectOptions(screen.getByLabelText(t.users.branch), '1')
    await userEvent.click(screen.getByLabelText(t.users.handlesCash))
    await userEvent.click(screen.getByRole('button', { name: t.users.create }))

    expect(await screen.findByText(t.users.createdNotice)).toBeInTheDocument()
    expect(createdBody).toMatchObject({
      email: 'nuevo@donchuy.test', branch: 1, role: 'CAJERO', username: 'nuevo_cajero', date_of_birth: '1998-06-20',
    })
  })

  it('crea un usuario nuevo dejando el correo en blanco — username es el único identificador obligatorio', async () => {
    mockLists()
    let createdBody: Record<string, unknown> | null = null
    server.use(
      http.post(USERS_URL, async ({ request }) => {
        createdBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 100, email: null, username: 'solo_username', is_active: true, branch: 1,
            role: 'CAJERO', capabilities: {}, date_of_birth: null, company: 1,
          },
          { status: 201 },
        )
      }),
    )
    renderScreen()
    await screen.findByText('admin@donchuy.test')

    await userEvent.type(screen.getByLabelText(t.users.username), 'solo_username')
    await userEvent.type(screen.getByLabelText(t.users.password), 'ClaveSegura2026!')
    await userEvent.selectOptions(screen.getByLabelText(t.users.branch), '1')
    await userEvent.click(screen.getByRole('button', { name: t.users.create }))

    expect(await screen.findByText(t.users.createdNotice)).toBeInTheDocument()
    expect(createdBody).toMatchObject({ username: 'solo_username', branch: 1, role: 'CAJERO' })
    expect(createdBody).not.toHaveProperty('email')
  })

  it('muestra un error legible cuando la creación falla (ej. usuario duplicado)', async () => {
    mockLists()
    server.use(
      http.post(USERS_URL, () => HttpResponse.json({ detail: 'Ya existe un usuario con este nombre de usuario.' }, { status: 400 })),
    )
    renderScreen()
    await screen.findByText('admin@donchuy.test')

    await userEvent.type(screen.getByLabelText(t.users.username), 'admin1')
    await userEvent.type(screen.getByLabelText(t.users.password), 'ClaveSegura2026!')
    await userEvent.selectOptions(screen.getByLabelText(t.users.branch), '1')
    await userEvent.click(screen.getByRole('button', { name: t.users.create }))

    expect(await screen.findByText('Ya existe un usuario con este nombre de usuario.')).toBeInTheDocument()
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
