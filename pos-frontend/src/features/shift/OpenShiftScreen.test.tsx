import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import { renderWithAuth } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeCashRegister, makeShift } from '@/test/fixtures'
import { t } from '@/i18n'
import { OpenShiftScreen } from './OpenShiftScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const REGISTERS_URL = `${BASE}/cash-registers/`
const OPEN_SHIFT_URL = `${BASE}/cash-shifts/open-shift/`

describe('OpenShiftScreen', () => {
  it('muestra las cajas disponibles y permite elegir una', async () => {
    server.use(
      http.get(REGISTERS_URL, () =>
        HttpResponse.json({
          count: 2,
          next: null,
          previous: null,
          results: [makeCashRegister({ id: 1, name: 'Caja 1' }), makeCashRegister({ id: 2, name: 'Caja 2' })],
        }),
      ),
    )

    renderWithAuth(<OpenShiftScreen onShiftOpened={vi.fn()} />)

    const select = (await screen.findByLabelText(t.shift.register)) as HTMLSelectElement
    expect(screen.getByRole('option', { name: 'Caja 1' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Caja 2' })).toBeInTheDocument()
    // Preselecciona la primera por default:
    expect(select.value).toBe('1')

    await userEvent.selectOptions(select, '2')
    expect(select.value).toBe('2')
  })

  it('solo muestra cajas de la sucursal del cajero', async () => {
    server.use(
      http.get(REGISTERS_URL, () =>
        HttpResponse.json({
          count: 2,
          next: null,
          previous: null,
          results: [
            makeCashRegister({ id: 1, branch: 1, name: 'Caja de mi sucursal' }),
            makeCashRegister({ id: 2, branch: 99, name: 'Caja de otra sucursal' }),
          ],
        }),
      ),
    )

    // fakeAuthValue() por default trae branch.id = 1 (ver fixtures.ts)
    renderWithAuth(<OpenShiftScreen onShiftOpened={vi.fn()} />)

    await screen.findByText('Caja de mi sucursal')
    expect(screen.queryByText('Caja de otra sucursal')).not.toBeInTheDocument()
  })

  it('envía la caja elegida y el fondo inicial correctamente al abrir turno', async () => {
    let capturedBody: unknown = null
    server.use(
      http.get(REGISTERS_URL, () =>
        HttpResponse.json({ count: 1, next: null, previous: null, results: [makeCashRegister({ id: 1 })] }),
      ),
      http.post(OPEN_SHIFT_URL, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(makeShift({ opening_balance: '350.00' }), { status: 201 })
      }),
    )

    const onShiftOpened = vi.fn()
    const user = userEvent.setup()
    renderWithAuth(<OpenShiftScreen onShiftOpened={onShiftOpened} />)

    await screen.findByLabelText(t.shift.register)
    const balanceInput = screen.getByLabelText(t.shift.openingBalance)
    await user.clear(balanceInput)
    await user.type(balanceInput, '350')
    await user.click(screen.getByRole('button', { name: t.shift.submit }))

    await vi.waitFor(() => expect(onShiftOpened).toHaveBeenCalledTimes(1))
    expect(capturedBody).toEqual({ cash_register_id: 1, opening_balance: '350' })
    expect(onShiftOpened).toHaveBeenCalledWith(expect.objectContaining({ opening_balance: '350.00' }))
  })

  it('muestra un mensaje si la sucursal no tiene cajas registradas', async () => {
    server.use(
      http.get(REGISTERS_URL, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
    )

    renderWithAuth(<OpenShiftScreen onShiftOpened={vi.fn()} />)

    expect(await screen.findByText(t.shift.noRegisters)).toBeInTheDocument()
  })
})
