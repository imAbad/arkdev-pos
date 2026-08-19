import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { AuthContext } from '@/features/auth/AuthProvider'
import { fakeAuthValue } from '@/test/test-utils'
import { server } from '@/test/server'
import { makeBranch, makeProduct, makeProfile } from '@/test/fixtures'
import { t } from '@/i18n'
import { InventoryScreen } from './InventoryScreen'

const BASE = import.meta.env.VITE_API_BASE_URL
const PRODUCTS_URL = `${BASE}/products/`
const CATEGORIES_URL = `${BASE}/categories/`
const SUPPLIERS_URL = `${BASE}/suppliers/`
const BATCHES_URL = `${BASE}/batches/`

const YOGURT = makeProduct({ id: 1, name: 'Yogurt natural 1L', sku: 'YOG-1', category: 1, requires_batch: true })

function paginated<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results }
}

function mockCatalog(products = [YOGURT]) {
  server.use(
    http.get(PRODUCTS_URL, () => HttpResponse.json(paginated(products))),
    http.get(CATEGORIES_URL, () => HttpResponse.json(paginated([{ id: 1, name: 'Básicos', slug: 'basicos', is_active: true, company: 1 }]))),
    http.get(SUPPLIERS_URL, () => HttpResponse.json(paginated([]))),
  )
}

function renderScreen(profile: ReturnType<typeof makeProfile>) {
  const auth = fakeAuthValue({ profile, branch: makeBranch({ id: 1 }) })
  return render(
    <AuthContext.Provider value={auth}>
      <InventoryScreen />
    </AuthContext.Provider>,
  )
}

describe('InventoryScreen', () => {
  it('lista los productos del catálogo', async () => {
    mockCatalog()
    renderScreen(makeProfile({ role: 'ADMINISTRADOR' }))

    expect(await screen.findByText('Yogurt natural 1L')).toBeInTheDocument()
    expect(screen.getByText('YOG-1')).toBeInTheDocument()
  })

  it('muestra el stock actual sumado de lotes para un producto con control por lote', async () => {
    mockCatalog([makeProduct({ id: 1, name: 'Yogurt natural 1L', sku: 'YOG-1', requires_batch: true, current_stock: 23 })])
    renderScreen(makeProfile({ role: 'ADMINISTRADOR' }))

    await screen.findByText('Yogurt natural 1L')
    expect(screen.getByText('23')).toBeInTheDocument()
  })

  it('muestra un guion (no 0) para un producto sin control por lote — no se rastrea existencia', async () => {
    mockCatalog([makeProduct({ id: 1, name: 'Bolsa de mandado', sku: 'BOLSA-1', requires_batch: false, current_stock: null })])
    renderScreen(makeProfile({ role: 'ADMINISTRADOR' }))

    await screen.findByText('Bolsa de mandado')
    expect(screen.getByTitle(t.inventory.stockNotTracked)).toHaveTextContent('—')
  })

  it('pide el catálogo escopado a la sucursal de la sesión', async () => {
    let capturedBranch: string | null = null
    server.use(
      http.get(PRODUCTS_URL, ({ request }) => {
        capturedBranch = new URL(request.url).searchParams.get('branch')
        return HttpResponse.json(paginated([YOGURT]))
      }),
      http.get(CATEGORIES_URL, () => HttpResponse.json(paginated([{ id: 1, name: 'Básicos', slug: 'basicos', is_active: true, company: 1 }]))),
      http.get(SUPPLIERS_URL, () => HttpResponse.json(paginated([]))),
    )
    renderScreen(makeProfile({ role: 'ADMINISTRADOR' }))

    await screen.findByText('Yogurt natural 1L')
    expect(capturedBranch).toBe('1')
  })

  it('el buscador filtra por nombre, sku o categoría', async () => {
    mockCatalog([YOGURT, makeProduct({ id: 2, name: 'Refresco de cola 600ml', sku: 'REF-600', category: 1 })])
    const user = userEvent.setup()
    renderScreen(makeProfile({ role: 'ADMINISTRADOR' }))

    await screen.findByText('Yogurt natural 1L')
    await user.type(screen.getByLabelText(t.inventory.searchPlaceholder), 'yogurt')

    expect(screen.getByText('Yogurt natural 1L')).toBeInTheDocument()
    expect(screen.queryByText('Refresco de cola 600ml')).not.toBeInTheDocument()
  })

  it('ADMINISTRADOR puede editar un producto (PATCH)', async () => {
    mockCatalog()
    let capturedBody: unknown = null
    server.use(
      http.patch(`${PRODUCTS_URL}1/`, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({ ...YOGURT, name: 'Yogurt natural 1L (editado)' })
      }),
    )
    const user = userEvent.setup()
    renderScreen(makeProfile({ role: 'ADMINISTRADOR' }))

    await screen.findByText('Yogurt natural 1L')
    await user.click(screen.getByRole('button', { name: t.inventory.edit }))
    const nameInput = screen.getByLabelText(t.inventory.name)
    await user.clear(nameInput)
    await user.type(nameInput, 'Yogurt natural 1L (editado)')
    await user.click(screen.getByRole('button', { name: t.inventory.save }))

    expect(await screen.findByText('Yogurt natural 1L (editado)')).toBeInTheDocument()
    expect(capturedBody).toMatchObject({ name: 'Yogurt natural 1L (editado)' })
  })

  it('un Supervisor no ve el botón de Editar pero sí el de Lotes', async () => {
    mockCatalog()
    renderScreen(makeProfile({ role: 'CAJERO', capabilities: { can_authorize_exceptions: true } }))

    await screen.findByText('Yogurt natural 1L')
    expect(screen.queryByRole('button', { name: t.inventory.edit })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.inventory.colBatches })).toBeInTheDocument()
  })

  it('Supervisor puede agregar un lote', async () => {
    mockCatalog()
    server.use(http.get(BATCHES_URL, () => HttpResponse.json(paginated([]))))
    let capturedBody: unknown = null
    server.use(
      http.post(BATCHES_URL, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({
          id: 5, product: 1, branch: 1, batch_number: 'L-NUEVO', initial_quantity: 10,
          current_quantity: 10, expiration_date: '2030-01-01', received_date: '2026-08-18', company: 1,
        })
      }),
    )
    const user = userEvent.setup()
    renderScreen(makeProfile({ role: 'CAJERO', capabilities: { can_authorize_exceptions: true } }))

    await screen.findByText('Yogurt natural 1L')
    await user.click(screen.getByRole('button', { name: t.inventory.colBatches }))
    await screen.findByText(t.inventory.noBatchesYet)

    await user.type(screen.getByLabelText(t.inventory.batchNumber), 'L-NUEVO')
    await user.clear(screen.getByLabelText(t.inventory.initialQuantity))
    await user.type(screen.getByLabelText(t.inventory.initialQuantity), '10')
    await user.type(screen.getByLabelText(t.inventory.expirationDate), '2030-01-01')
    await user.click(screen.getByRole('button', { name: t.inventory.addBatch }))

    expect(capturedBody).toMatchObject({ product: 1, branch: 1, batch_number: 'L-NUEVO', initial_quantity: 10 })
  })
})
