import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import { renderWithAuth } from '@/test/test-utils'
import { t } from '@/i18n'
import { LoginScreen } from './LoginScreen'

// Corrección de sesión: un solo formulario de login — username y email
// son dos identificadores de la MISMA cuenta, no dos mecanismos
// separados. No debe quedar ningún campo de fecha de nacimiento aquí.
describe('LoginScreen', () => {
  it('muestra un único formulario: identificador + contraseña', () => {
    renderWithAuth(<LoginScreen />)

    expect(screen.getByLabelText(t.login.identifier)).toBeInTheDocument()
    expect(screen.getByLabelText(t.login.password)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.login.submit })).toBeInTheDocument()
    expect(screen.queryByLabelText(/fecha de nacimiento/i)).not.toBeInTheDocument()
  })

  it('envía login() con lo que haya en el campo identificador, sea username o correo', async () => {
    const login = vi.fn().mockResolvedValue(true)
    renderWithAuth(<LoginScreen />, { login })

    await userEvent.type(screen.getByLabelText(t.login.identifier), 'cajero1')
    await userEvent.type(screen.getByLabelText(t.login.password), 'ClaveSegura2026!')
    await userEvent.click(screen.getByRole('button', { name: t.login.submit }))

    expect(login).toHaveBeenCalledWith('cajero1', 'ClaveSegura2026!')
  })

  it('envía login() igual cuando el identificador es un correo', async () => {
    const login = vi.fn().mockResolvedValue(true)
    renderWithAuth(<LoginScreen />, { login })

    await userEvent.type(screen.getByLabelText(t.login.identifier), 'admin@donchuy.test')
    await userEvent.type(screen.getByLabelText(t.login.password), 'ClaveSegura2026!')
    await userEvent.click(screen.getByRole('button', { name: t.login.submit }))

    expect(login).toHaveBeenCalledWith('admin@donchuy.test', 'ClaveSegura2026!')
  })

  it('muestra el error del login cuando loginError está presente', () => {
    renderWithAuth(<LoginScreen />, { loginError: t.login.errorInvalid })

    expect(screen.getByRole('alert')).toHaveTextContent(t.login.errorInvalid)
  })
})
