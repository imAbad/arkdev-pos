import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { server } from '@/test/server'
import { makeClient } from '@/test/fixtures'
import { t } from '@/i18n'
import { PaymentPanel } from './PaymentPanel'

const BASE = import.meta.env.VITE_API_BASE_URL
const CLIENTS_URL = `${BASE}/clients/`

// Observación de sesión (ronda de 4 piezas, punto 3): venta a crédito —
// confirmado con evidencia de código que nunca se había construido esta
// pantalla (PaymentPanel excluía CREDIT a propósito). El backend
// (Client/CreditAccount/charge_credit) ya existía completo.
function renderPanel(overrides: Partial<React.ComponentProps<typeof PaymentPanel>> = {}) {
  const onCharge = vi.fn()
  const onChangeMethod = vi.fn()
  const onChangeCreditClient = vi.fn()
  render(
    <PaymentPanel
      total={100}
      method="CASH"
      onChangeMethod={onChangeMethod}
      cashReceived="100"
      onChangeCashReceived={() => {}}
      reference=""
      onChangeReference={() => {}}
      creditClient={null}
      onChangeCreditClient={onChangeCreditClient}
      onCharge={onCharge}
      submitting={false}
      disabled={false}
      {...overrides}
    />,
  )
  return { onCharge, onChangeMethod, onChangeCreditClient }
}

describe('PaymentPanel — Crédito (fiado)', () => {
  it('muestra Crédito como opción junto a Efectivo/Tarjeta/Transferencia', () => {
    renderPanel()
    expect(screen.getByRole('button', { name: t.sale.methodCredit })).toBeInTheDocument()
  })

  it('al elegir Crédito sin cliente todavía, "Cobrar" queda deshabilitado', async () => {
    const user = userEvent.setup()
    const { onChangeMethod } = renderPanel()
    await user.click(screen.getByRole('button', { name: t.sale.methodCredit }))
    expect(onChangeMethod).toHaveBeenCalledWith('CREDIT')
  })

  it('con un cliente ya elegido, muestra su crédito disponible real y habilita "Cobrar"', () => {
    renderPanel({ method: 'CREDIT', creditClient: makeClient({ available_credit: '380.00' }) })
    expect(screen.getByText(/380.00/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.sale.charge })).toBeEnabled()
  })

  it('sin cliente elegido, "Cobrar" está deshabilitado aunque el resto del carrito esté listo', () => {
    renderPanel({ method: 'CREDIT', creditClient: null })
    expect(screen.getByRole('button', { name: t.sale.charge })).toBeDisabled()
  })

  it('busca un cliente existente y lo selecciona', async () => {
    server.use(
      http.get(CLIENTS_URL, ({ request }) => {
        const search = new URL(request.url).searchParams.get('search')
        const results = search === 'lupe' ? [makeClient({ id: 9, name: 'Doña Lupe' })] : []
        return HttpResponse.json({ count: results.length, next: null, previous: null, results })
      }),
    )
    const user = userEvent.setup()
    const { onChangeCreditClient } = renderPanel({ method: 'CREDIT' })

    await user.type(screen.getByLabelText(t.sale.creditClientLabel), 'lupe')
    const result = await screen.findByRole('button', { name: /Doña Lupe/ })
    await user.click(result)

    expect(onChangeCreditClient).toHaveBeenCalledWith(expect.objectContaining({ id: 9, name: 'Doña Lupe' }))
  })

  it('crea un cliente rápido con nombre y teléfono cuando no existe', async () => {
    let capturedBody: unknown = null
    server.use(
      http.get(CLIENTS_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.post(CLIENTS_URL, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(
          makeClient({ id: 10, name: 'Cliente nuevo', phone: '5550001111', credit_limit: '0.00', available_credit: '0.00' }),
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    const { onChangeCreditClient } = renderPanel({ method: 'CREDIT' })

    await user.click(screen.getByRole('button', { name: t.sale.creditNewClient }))
    await user.type(screen.getByLabelText(t.sale.creditNewClientName), 'Cliente nuevo')
    await user.type(screen.getByLabelText(t.sale.creditNewClientPhone), '5550001111')
    await user.click(screen.getByRole('button', { name: t.sale.creditNewClientCreate }))

    expect(await screen.findByText(/Cliente nuevo/)).toBeInTheDocument()
    expect(capturedBody).toEqual({ name: 'Cliente nuevo', phone: '5550001111' })
    expect(onChangeCreditClient).toHaveBeenCalledWith(expect.objectContaining({ id: 10, name: 'Cliente nuevo' }))
  })

  it('"Cambiar cliente" regresa al buscador', async () => {
    const user = userEvent.setup()
    const { onChangeCreditClient } = renderPanel({ method: 'CREDIT', creditClient: makeClient() })

    await user.click(screen.getByRole('button', { name: t.sale.creditChangeClient }))

    expect(onChangeCreditClient).toHaveBeenCalledWith(null)
  })
})
