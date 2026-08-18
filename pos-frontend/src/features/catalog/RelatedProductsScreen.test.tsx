import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeProduct, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { RelatedProductsScreen } from './RelatedProductsScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const PRODUCTS_URL = `${BASE}/products/`

const PAN = makeProduct({ id: 1, name: 'Pan de caja', sku: 'PAN-1', sale_price: '32.00' })
const MANTEQUILLA = makeProduct({ id: 2, name: 'Mantequilla', sku: 'MANT-1', sale_price: '45.00' })

function mockSearch(byQuery: Record<string, ReturnType<typeof makeProduct>[]>) {
  server.use(
    http.get(PRODUCTS_URL, ({ request }) => {
      const query = new URL(request.url).searchParams.get('search') ?? ''
      const results = byQuery[query] ?? []
      return HttpResponse.json({ count: results.length, next: null, previous: null, results })
    }),
  )
}

function renderScreen() {
  const auth = fakeAuthValue({ profile: makeProfile({ role: 'ADMINISTRADOR' }) })
  return render(
    <AuthContext.Provider value={auth}>
      <RelatedProductsScreen />
    </AuthContext.Provider>,
  )
}

describe('RelatedProductsScreen', () => {
  it('elige un producto y muestra que todavía no tiene relacionados', async () => {
    mockSearch({ pan: [PAN] })
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText(t.relatedProducts.chooseProduct), 'pan')
    await user.click(await screen.findByRole('button', { name: /Pan de caja/ }))

    expect(screen.getByText('Pan de caja')).toBeInTheDocument()
    expect(screen.getByText(t.relatedProducts.noneYet)).toBeInTheDocument()
  })

  it('agregar un relacionado hace PATCH con el id nuevo y lo muestra', async () => {
    let capturedBody: unknown = null
    mockSearch({ pan: [PAN], mantequilla: [MANTEQUILLA] })
    server.use(
      http.patch(`${BASE}/products/1/`, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({
          ...PAN,
          related_products: [2],
          related_products_detail: [{ id: 2, name: 'Mantequilla', sale_price: '45.00' }],
        })
      }),
    )

    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText(t.relatedProducts.chooseProduct), 'pan')
    await user.click(await screen.findByRole('button', { name: /Pan de caja/ }))

    await user.type(screen.getByLabelText(t.relatedProducts.addRelated), 'mantequilla')
    await user.click(await screen.findByRole('button', { name: /Mantequilla/ }))

    expect(capturedBody).toEqual({ related_products: [2] })
    await screen.findByText(t.relatedProducts.currentlyRelated)
    expect(screen.getAllByText('Mantequilla').length).toBeGreaterThan(0)
  })

  it('quitar un relacionado hace PATCH sin ese id', async () => {
    let capturedBody: unknown = null
    const panWithRelation = makeProduct({
      ...PAN,
      related_products: [2],
      related_products_detail: [{ id: 2, name: 'Mantequilla', sale_price: '45.00' }],
    })
    mockSearch({ pan: [panWithRelation] })
    server.use(
      http.patch(`${BASE}/products/1/`, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({ ...PAN, related_products: [], related_products_detail: [] })
      }),
    )

    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText(t.relatedProducts.chooseProduct), 'pan')
    await user.click(await screen.findByRole('button', { name: /Pan de caja/ }))

    await user.click(screen.getByRole('button', { name: t.relatedProducts.remove }))

    expect(capturedBody).toEqual({ related_products: [] })
    await screen.findByText(t.relatedProducts.noneYet)
  })
})
