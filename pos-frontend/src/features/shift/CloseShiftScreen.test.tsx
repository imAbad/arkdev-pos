import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import { renderWithAuth } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeShift } from '@/test/fixtures'
import { t } from '@/i18n'
import { CloseShiftScreen } from './CloseShiftScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const CLOSE_SHIFT_URL = `${BASE}/cash-shifts/1/close-shift/`

describe('CloseShiftScreen', () => {
  it('declara actual_* sin mostrar expected_* antes de enviar (arqueo ciego)', () => {
    renderWithAuth(<CloseShiftScreen shift={makeShift({ id: 1 })} onCancel={vi.fn()} />)

    expect(screen.getByLabelText(t.closeShift.actualCash)).toBeInTheDocument()
    expect(screen.getByLabelText(t.closeShift.actualVoucher)).toBeInTheDocument()
    expect(screen.queryByText(t.closeShift.expected)).not.toBeInTheDocument()
  })

  it('envía lo declarado y muestra "Coincide" en verde cuando no hay diferencia', async () => {
    server.use(
      http.post(CLOSE_SHIFT_URL, () =>
        HttpResponse.json(
          makeShift({
            id: 1,
            status: 'CLOSED',
            expected_closing_balance: '500.00',
            actual_closing_balance: '500.00',
            cash_difference: '0.00',
            expected_voucher_total: '0.00',
            actual_voucher_total: '0.00',
            voucher_difference: '0.00',
          }),
        ),
      ),
    )

    const user = userEvent.setup()
    renderWithAuth(<CloseShiftScreen shift={makeShift({ id: 1 })} onCancel={vi.fn()} />)

    await user.clear(screen.getByLabelText(t.closeShift.actualCash))
    await user.type(screen.getByLabelText(t.closeShift.actualCash), '500')
    await user.click(screen.getByRole('button', { name: t.closeShift.submit }))

    expect(await screen.findAllByText(t.closeShift.matches)).toHaveLength(2)
    expect(screen.queryByLabelText(t.closeShift.actualCash)).not.toBeInTheDocument()
  })

  it('muestra "Sobrante" cuando lo contado es mayor a lo esperado', async () => {
    server.use(
      http.post(CLOSE_SHIFT_URL, () =>
        HttpResponse.json(
          makeShift({
            id: 1,
            status: 'CLOSED',
            expected_closing_balance: '500.00',
            actual_closing_balance: '520.00',
            cash_difference: '20.00',
            expected_voucher_total: '0.00',
            actual_voucher_total: '0.00',
            voucher_difference: '0.00',
          }),
        ),
      ),
    )

    const user = userEvent.setup()
    renderWithAuth(<CloseShiftScreen shift={makeShift({ id: 1 })} onCancel={vi.fn()} />)

    await user.clear(screen.getByLabelText(t.closeShift.actualCash))
    await user.type(screen.getByLabelText(t.closeShift.actualCash), '520')
    await user.click(screen.getByRole('button', { name: t.closeShift.submit }))

    expect(await screen.findByText(t.closeShift.surplus)).toBeInTheDocument()
  })

  it('muestra "Faltante" cuando lo contado es menor a lo esperado', async () => {
    server.use(
      http.post(CLOSE_SHIFT_URL, () =>
        HttpResponse.json(
          makeShift({
            id: 1,
            status: 'CLOSED',
            expected_closing_balance: '500.00',
            actual_closing_balance: '480.00',
            cash_difference: '-20.00',
            expected_voucher_total: '0.00',
            actual_voucher_total: '0.00',
            voucher_difference: '0.00',
          }),
        ),
      ),
    )

    const user = userEvent.setup()
    renderWithAuth(<CloseShiftScreen shift={makeShift({ id: 1 })} onCancel={vi.fn()} />)

    await user.clear(screen.getByLabelText(t.closeShift.actualCash))
    await user.type(screen.getByLabelText(t.closeShift.actualCash), '480')
    await user.click(screen.getByRole('button', { name: t.closeShift.submit }))

    expect(await screen.findByText(t.closeShift.shortage)).toBeInTheDocument()
  })

  it('el botón "Volver a vender" llama a onCancel sin cerrar el turno', async () => {
    const onCancel = vi.fn()
    const user = userEvent.setup()
    renderWithAuth(<CloseShiftScreen shift={makeShift({ id: 1 })} onCancel={onCancel} />)

    await user.click(screen.getByRole('button', { name: t.closeShift.cancel }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
