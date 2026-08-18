import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { t } from '@/i18n'
import { CrossSellSuggestion } from './CrossSellSuggestion'

const MANTEQUILLA = { id: 2, name: 'Mantequilla', sale_price: '32.00' }

describe('CrossSellSuggestion', () => {
  it('no renderiza nada si no hay sugerencias', () => {
    const { container } = render(<CrossSellSuggestion items={[]} onAdd={vi.fn()} onDismiss={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('muestra la sugerencia y permite agregarla con un toque', async () => {
    const onAdd = vi.fn()
    const user = userEvent.setup()
    render(<CrossSellSuggestion items={[MANTEQUILLA]} onAdd={onAdd} onDismiss={vi.fn()} />)

    expect(screen.getByText('Mantequilla')).toBeInTheDocument()
    expect(screen.getByText('$32.00')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t.sale.crossSellAdd }))
    expect(onAdd).toHaveBeenCalledWith(2)
  })

  it('se puede descartar sin agregar nada', async () => {
    const onDismiss = vi.fn()
    const user = userEvent.setup()
    render(<CrossSellSuggestion items={[MANTEQUILLA]} onAdd={vi.fn()} onDismiss={onDismiss} />)

    await user.click(screen.getByRole('button', { name: t.sale.crossSellDismiss }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
