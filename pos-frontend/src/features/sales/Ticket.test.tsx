import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { server } from '@/test/server'
import { makeSale } from '@/test/fixtures'
import { t } from '@/i18n'
import { Ticket } from './Ticket'

const BASE = import.meta.env.VITE_API_BASE_URL

const SALE = makeSale({
  id: 42,
  details: [
    { id: 1, product: 1, product_name: 'Arroz superextra 1kg', product_unit_type: 'PIEZA', batch: null, quantity: '1.000', unit_price: '24.00', tax_rate_applied: '0.00', tax_amount: '0.00', subtotal: '24.00' },
  ],
  payments: [{ id: 1, method: 'CASH', amount: '24.00', reference: '' }],
})

describe('Ticket — envío por correo (punto 6)', () => {
  it('el campo de correo se precarga con client_email si la venta tiene uno', () => {
    const sale = { ...SALE, client_email: 'cliente@test.com' }
    render(<Ticket sale={sale} businessName="Abarrotes Don Chuy" changeGiven={0} onBack={vi.fn()} />)
    expect(screen.getByLabelText(t.ticket.emailLabel)).toHaveValue('cliente@test.com')
  })

  it('envío exitoso muestra confirmación visible', async () => {
    let capturedBody: unknown = null
    server.use(
      http.post(`${BASE}/sales/42/send-ticket-email/`, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({ detail: 'Ticket enviado.' })
      }),
    )

    const user = userEvent.setup()
    render(<Ticket sale={SALE} businessName="Abarrotes Don Chuy" changeGiven={0} onBack={vi.fn()} />)

    await user.type(screen.getByLabelText(t.ticket.emailLabel), 'cliente@test.com')
    await user.click(screen.getByRole('button', { name: t.ticket.sendByEmail }))

    expect(await screen.findByText(t.ticket.sentByEmail)).toBeInTheDocument()
    expect(capturedBody).toEqual({ email: 'cliente@test.com', change_given: undefined })
  })

  it('manda el cambio entregado cuando aplica (pago en efectivo con cambio)', async () => {
    let capturedBody: unknown = null
    server.use(
      http.post(`${BASE}/sales/42/send-ticket-email/`, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({ detail: 'Ticket enviado.' })
      }),
    )

    const user = userEvent.setup()
    render(<Ticket sale={SALE} businessName="Abarrotes Don Chuy" changeGiven={6} onBack={vi.fn()} />)

    await user.type(screen.getByLabelText(t.ticket.emailLabel), 'cliente@test.com')
    await user.click(screen.getByRole('button', { name: t.ticket.sendByEmail }))

    await screen.findByText(t.ticket.sentByEmail)
    expect(capturedBody).toEqual({ email: 'cliente@test.com', change_given: '6.00' })
  })

  it('si el backend no puede enviar (SMTP falla, 502), muestra un mensaje humano sin romper la pantalla', async () => {
    server.use(
      http.post(`${BASE}/sales/42/send-ticket-email/`, () =>
        HttpResponse.json({ detail: 'No se pudo enviar el correo. Verifica la dirección o intenta de nuevo más tarde.' }, { status: 502 }),
      ),
    )

    const user = userEvent.setup()
    render(<Ticket sale={SALE} businessName="Abarrotes Don Chuy" changeGiven={0} onBack={vi.fn()} />)

    await user.type(screen.getByLabelText(t.ticket.emailLabel), 'cliente@test.com')
    await user.click(screen.getByRole('button', { name: t.ticket.sendByEmail }))

    expect(await screen.findByText('No se pudo enviar el correo. Verifica la dirección o intenta de nuevo más tarde.')).toBeInTheDocument()
    expect(screen.queryByText(t.ticket.sentByEmail)).not.toBeInTheDocument()
  })

  it('el botón de enviar está deshabilitado sin un correo escrito', () => {
    render(<Ticket sale={SALE} businessName="Abarrotes Don Chuy" changeGiven={0} onBack={vi.fn()} />)
    expect(screen.getByRole('button', { name: t.ticket.sendByEmail })).toBeDisabled()
  })
})

describe('Ticket — cancelar/devolver venta (punto 10)', () => {
  it('cancela la venta con credenciales de supervisor válidas y muestra el estado actualizado', async () => {
    server.use(
      http.post(`${BASE}/auth/authorize-exception/`, () =>
        HttpResponse.json({ token: 'tok-123', supervisor_email: 'admin@donchuy.test', reason: '', expires_at: '2026-08-18T13:00:00Z' }),
      ),
      http.post(`${BASE}/sales/42/cancel/`, async ({ request }) => {
        const body = (await request.json()) as { supervisor_authorization_token: string }
        expect(body.supervisor_authorization_token).toBe('tok-123')
        return HttpResponse.json({ ...SALE, status: 'REFUNDED' })
      }),
    )

    const user = userEvent.setup()
    render(<Ticket sale={SALE} businessName="Abarrotes Don Chuy" changeGiven={0} onBack={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: t.ticket.cancelSale }))
    await user.type(screen.getByLabelText(t.ticket.supervisorEmail), 'admin@donchuy.test')
    await user.type(screen.getByLabelText(t.ticket.supervisorPassword), 'demo1234')
    await user.click(screen.getByRole('button', { name: t.ticket.confirmCancelSale }))

    expect(await screen.findByText(t.ticket.statusRefunded)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.ticket.cancelSale })).not.toBeInTheDocument()
  })

  it('muestra un error legible si las credenciales de supervisor son inválidas', async () => {
    server.use(
      http.post(`${BASE}/auth/authorize-exception/`, () =>
        HttpResponse.json({ detail: 'Credenciales de supervisor inválidas o sin autoridad para autorizar.' }, { status: 403 }),
      ),
    )

    const user = userEvent.setup()
    render(<Ticket sale={SALE} businessName="Abarrotes Don Chuy" changeGiven={0} onBack={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: t.ticket.cancelSale }))
    await user.type(screen.getByLabelText(t.ticket.supervisorEmail), 'admin@donchuy.test')
    await user.type(screen.getByLabelText(t.ticket.supervisorPassword), 'contraseña-mala')
    await user.click(screen.getByRole('button', { name: t.ticket.confirmCancelSale }))

    expect(
      await screen.findByText('Credenciales de supervisor inválidas o sin autoridad para autorizar.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.ticket.confirmCancelSale })).toBeInTheDocument()
  })

  it('una venta ya devuelta no muestra el botón de cancelar', () => {
    render(<Ticket sale={{ ...SALE, status: 'REFUNDED' }} businessName="Abarrotes Don Chuy" changeGiven={0} onBack={vi.fn()} />)
    expect(screen.getByText(t.ticket.statusRefunded)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.ticket.cancelSale })).not.toBeInTheDocument()
  })
})
