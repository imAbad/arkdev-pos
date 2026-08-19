import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithAuth } from '@/test/test-utils'
import { t } from '@/i18n'
import { LoginScreen } from './LoginScreen'

// Punto 5: el login alterno (usuario + fecha de nacimiento) coexiste con
// el de correo+contraseña — "ambas visibles, ninguna oculta la otra".
// Estos tests fijan justo eso: ambos formularios están en el DOM a la vez,
// sin pestañas que escondan uno al abrir el otro.
describe('LoginScreen', () => {
  it('muestra el formulario de correo+contraseña y el de usuario a la vez, ninguno oculto', () => {
    renderWithAuth(<LoginScreen />)

    expect(screen.getByLabelText(t.login.email)).toBeInTheDocument()
    expect(screen.getByLabelText(t.login.password)).toBeInTheDocument()
    expect(screen.getByLabelText(t.login.username)).toBeInTheDocument()
    expect(screen.getByLabelText(t.login.dateOfBirth)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.login.submit })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.login.usernameSubmit })).toBeInTheDocument()
  })

  it('envía el formulario de correo+contraseña con login()', async () => {
    const login = vi.fn().mockResolvedValue(true)
    renderWithAuth(<LoginScreen />, { login })

    await userEvent.type(screen.getByLabelText(t.login.email), 'admin@donchuy.test')
    await userEvent.type(screen.getByLabelText(t.login.password), 'ClaveSegura2026!')
    await userEvent.click(screen.getByRole('button', { name: t.login.submit }))

    expect(login).toHaveBeenCalledWith('admin@donchuy.test', 'ClaveSegura2026!')
  })

  it('envía el formulario de usuario+fecha de nacimiento con loginWithUsername()', async () => {
    const loginWithUsername = vi.fn().mockResolvedValue(true)
    renderWithAuth(<LoginScreen />, { loginWithUsername })

    await userEvent.type(screen.getByLabelText(t.login.username), 'cajero1')
    fireEvent.change(screen.getByLabelText(t.login.dateOfBirth), { target: { value: '1998-06-20' } })
    await userEvent.click(screen.getByRole('button', { name: t.login.usernameSubmit }))

    expect(loginWithUsername).toHaveBeenCalledWith('cajero1', '1998-06-20')
  })

  it('muestra el error del login cuando loginError está presente', () => {
    renderWithAuth(<LoginScreen />, { loginError: t.login.usernameErrorInvalid })

    expect(screen.getByRole('alert')).toHaveTextContent(t.login.usernameErrorInvalid)
  })
})
