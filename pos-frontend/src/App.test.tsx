// Integración real: App decide qué pantalla mostrar según AuthProvider
// (login -> ¿turno abierto? -> abrir turno o vender). Se prueba con
// <App/> completo + MSW, no con AuthProvider mockeado — es justo la
// orquestación que se quiere confirmar.
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import App from '@/App'
import { server } from '@/test/server'
import { t } from '@/i18n'

const TOKEN_URL = `${import.meta.env.VITE_API_BASE_URL}/auth/token/`

async function login(identifier = 'cajero@donchuy.test', password = 'cajero123') {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByText(t.login.title)
  await user.type(screen.getByLabelText(t.login.identifier), identifier)
  await user.type(screen.getByLabelText(t.login.password), password)
  await user.click(screen.getByRole('button', { name: t.login.submit }))
  return user
}

describe('App — login navega a la siguiente pantalla', () => {
  it('con credenciales correctas, pasa de login a abrir turno (no tiene turno abierto)', async () => {
    await login()
    expect(await screen.findByText(t.shift.title)).toBeInTheDocument()
    expect(screen.queryByText(t.login.title)).not.toBeInTheDocument()
  })

  it('con credenciales incorrectas, muestra el mensaje en español sin romper la pantalla', async () => {
    server.use(
      http.post(TOKEN_URL, () =>
        HttpResponse.json({ detail: 'No active account found with the given credentials' }, { status: 401 }),
      ),
    )

    await login('cajero@donchuy.test', 'contraseña-mala')

    expect(await screen.findByText(t.login.errorInvalid)).toBeInTheDocument()
    // Nada de texto crudo del backend en inglés:
    expect(screen.queryByText(/no active account/i)).not.toBeInTheDocument()
    // La pantalla de login sigue ahí y usable, no se rompió:
    expect(screen.getByText(t.login.title)).toBeInTheDocument()
    expect(screen.getByLabelText(t.login.identifier)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.login.submit })).toBeEnabled()
  })
})
