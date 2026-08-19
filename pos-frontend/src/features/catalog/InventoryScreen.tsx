import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency, formatDate } from '@/lib/format'
import { useAuth } from '@/features/auth/AuthProvider'
import { isAdministrator, isAdministratorOrSupervisor } from '@/lib/permissions'
import {
  createBatch,
  createProduct,
  listAllProducts,
  listBatchesForProduct,
  listCategories,
  listSuppliers,
  updateProduct,
  type ProductInput,
} from '@/services/api/catalogApi'
import { t } from '@/i18n'
import type { Batch, Category, Product, Supplier, UnitType } from '@/types/api'

const UNIT_OPTIONS: { value: UnitType; label: string }[] = [
  { value: 'PIEZA', label: 'Pieza' },
  { value: 'KG', label: 'Kilogramo' },
  { value: 'GRAMO', label: 'Gramo' },
  { value: 'LITRO', label: 'Litro' },
  { value: 'PAQUETE', label: 'Paquete' },
  { value: 'SERVICIO', label: 'Servicio' },
]

type Panel = { type: 'new' } | { type: 'edit'; product: Product } | { type: 'batches'; product: Product }

/** Observación de sesión, punto 2: el CRUD de catálogo/inventario ya
 * existía completo en el backend desde el punto 8 (Category/Supplier/
 * Product/Batch, con el mismo split de permisos que esta pantalla
 * refleja) — solo faltaba una pantalla que lo consumiera, no había
 * ninguna todavía. */
export function InventoryScreen() {
  const { profile, branch } = useAuth()
  const isAdmin = isAdministrator(profile)
  const isAdminOrSupervisor = isAdministratorOrSupervisor(profile)

  const [products, setProducts] = useState<Product[] | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [panel, setPanel] = useState<Panel | null>(null)

  function load() {
    setError(null)
    Promise.all([listAllProducts(branch?.id), listCategories(), listSuppliers()])
      .then(([productsResult, categoriesResult, suppliersResult]) => {
        setProducts(productsResult)
        setCategories(categoriesResult)
        setSuppliers(suppliersResult)
      })
      .catch((err) => setError(apiErrorMessage(err, t.inventory.errorGeneric)))
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [branch?.id])

  function categoryName(id: number): string {
    return categories.find((c) => c.id === id)?.name ?? `#${id}`
  }

  const normalizedQuery = query.trim().toLowerCase()
  const filtered = (products ?? []).filter((product) => {
    if (!normalizedQuery) return true
    return (
      product.name.toLowerCase().includes(normalizedQuery) ||
      product.sku.toLowerCase().includes(normalizedQuery) ||
      categoryName(product.category).toLowerCase().includes(normalizedQuery)
    )
  })

  function handleSaved(product: Product) {
    setProducts((prev) => {
      if (prev === null) return prev
      const exists = prev.some((p) => p.id === product.id)
      return exists ? prev.map((p) => (p.id === product.id ? product : p)) : [product, ...prev]
    })
    setPanel(null)
  }

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-ink">{t.inventory.title}</h1>
          <p className="mt-2 text-lg text-ink/70">{t.inventory.subtitle}</p>
        </div>
        {isAdmin && (
          <Button type="button" variant="confirm" onClick={() => setPanel({ type: 'new' })}>
            {t.inventory.newProduct}
          </Button>
        )}
      </div>

      <Input
        aria-label={t.inventory.searchPlaceholder}
        placeholder={t.inventory.searchPlaceholder}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      {error && (
        <p role="alert" className="text-lg font-medium text-cancel">
          {error}
        </p>
      )}

      {panel?.type === 'new' && (
        <ProductForm
          categories={categories}
          suppliers={suppliers}
          onSaved={handleSaved}
          onCancel={() => setPanel(null)}
        />
      )}
      {panel?.type === 'edit' && (
        <ProductForm
          product={panel.product}
          categories={categories}
          suppliers={suppliers}
          onSaved={handleSaved}
          onCancel={() => setPanel(null)}
        />
      )}
      {panel?.type === 'batches' && branch && (
        <BatchesPanel product={panel.product} branchId={branch.id} onClose={() => setPanel(null)} />
      )}

      {!error && products === null && <p className="text-lg text-ink/70">{t.inventory.loading}</p>}

      {!error && products !== null && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-max text-left text-lg">
            <thead>
              <tr className="border-b-2 border-border">
                <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.inventory.colProduct}</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.inventory.colSku}</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.inventory.colCategory}</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.inventory.colCost}</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.inventory.colPrice}</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.inventory.colCurrentStock}</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.inventory.colMinStock}</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((product) => (
                <tr key={product.id} className="border-b border-border">
                  <td className="px-3 py-2">{product.name}</td>
                  <td className="px-3 py-2">{product.sku}</td>
                  <td className="px-3 py-2">{categoryName(product.category)}</td>
                  <td className="px-3 py-2">{formatCurrency(product.cost_price)}</td>
                  <td className="px-3 py-2">{formatCurrency(product.sale_price)}</td>
                  <td className="px-3 py-2">
                    {product.current_stock === null ? (
                      <span className="text-ink/50" title={t.inventory.stockNotTracked}>
                        —
                      </span>
                    ) : (
                      product.current_stock
                    )}
                  </td>
                  <td className="px-3 py-2">{product.min_stock}</td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      {isAdmin && (
                        <Button type="button" variant="neutral" size="compact" onClick={() => setPanel({ type: 'edit', product })}>
                          {t.inventory.edit}
                        </Button>
                      )}
                      {isAdminOrSupervisor && product.requires_batch && (
                        <Button
                          type="button"
                          variant="neutral"
                          size="compact"
                          onClick={() => setPanel({ type: 'batches', product })}
                        >
                          {t.inventory.colBatches}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ProductForm({
  product,
  categories,
  suppliers,
  onSaved,
  onCancel,
}: {
  product?: Product
  categories: Category[]
  suppliers: Supplier[]
  onSaved: (product: Product) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(product?.name ?? '')
  const [sku, setSku] = useState(product?.sku ?? '')
  const [barcode, setBarcode] = useState(product?.barcode ?? '')
  const [categoryId, setCategoryId] = useState<number | ''>(product?.category ?? '')
  const [supplierId, setSupplierId] = useState<number | ''>(product?.supplier ?? '')
  const [unitType, setUnitType] = useState<UnitType>(product?.unit_type ?? 'PIEZA')
  const [requiresBatch, setRequiresBatch] = useState(product?.requires_batch ?? false)
  const [costPrice, setCostPrice] = useState(product?.cost_price ?? '0.00')
  const [salePrice, setSalePrice] = useState(product?.sale_price ?? '0.00')
  const [taxRate, setTaxRate] = useState(product?.tax_rate ?? '0.00')
  const [minStock, setMinStock] = useState(String(product?.min_stock ?? 0))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (categoryId === '') return
    setSaving(true)
    setError(null)
    const input: ProductInput = {
      name,
      sku,
      barcode: barcode || null,
      category: categoryId,
      supplier: supplierId === '' ? null : supplierId,
      unit_type: unitType,
      requires_batch: requiresBatch,
      cost_price: costPrice,
      sale_price: salePrice,
      tax_rate: taxRate,
      min_stock: Number(minStock) || 0,
    }
    try {
      const saved = product ? await updateProduct(product.id, input) : await createProduct(input)
      onSaved(saved)
    } catch (err) {
      setError(apiErrorMessage(err, t.inventory.saveErrorGeneric))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <form onSubmit={(e) => void handleSubmit(e)} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <Label htmlFor="product-name">{t.inventory.name}</Label>
          <Input id="product-name" required value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="product-sku">{t.inventory.sku}</Label>
          <Input id="product-sku" required value={sku} onChange={(e) => setSku(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="product-barcode">{t.inventory.barcode}</Label>
          <Input id="product-barcode" value={barcode ?? ''} onChange={(e) => setBarcode(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="product-category">{t.inventory.category}</Label>
          <select
            id="product-category"
            required
            className="h-16 w-full rounded-2xl border-2 border-border bg-white px-5 text-xl text-ink"
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="" disabled>
              —
            </option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="product-supplier">{t.inventory.supplier}</Label>
          <select
            id="product-supplier"
            className="h-16 w-full rounded-2xl border-2 border-border bg-white px-5 text-xl text-ink"
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="">{t.inventory.none}</option>
            {suppliers.map((supplier) => (
              <option key={supplier.id} value={supplier.id}>
                {supplier.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="product-unit-type">{t.inventory.unitType}</Label>
          <select
            id="product-unit-type"
            className="h-16 w-full rounded-2xl border-2 border-border bg-white px-5 text-xl text-ink"
            value={unitType}
            onChange={(e) => setUnitType(e.target.value as UnitType)}
          >
            {UNIT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="product-cost">{t.inventory.costPrice}</Label>
          <Input id="product-cost" type="number" min="0" step="0.01" value={costPrice} onChange={(e) => setCostPrice(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="product-price">{t.inventory.salePrice}</Label>
          <Input id="product-price" type="number" min="0" step="0.01" value={salePrice} onChange={(e) => setSalePrice(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="product-tax">{t.inventory.taxRate}</Label>
          <Input id="product-tax" type="number" min="0" step="0.01" value={taxRate} onChange={(e) => setTaxRate(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="product-min-stock">{t.inventory.minStock}</Label>
          <Input id="product-min-stock" type="number" min="0" step="1" value={minStock} onChange={(e) => setMinStock(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 self-end pb-4 text-lg text-ink">
          <input type="checkbox" checked={requiresBatch} onChange={(e) => setRequiresBatch(e.target.checked)} />
          {t.inventory.requiresBatch}
        </label>

        <div className="flex items-end gap-3 sm:col-span-2 lg:col-span-3">
          <Button type="submit" variant="confirm" disabled={saving}>
            {saving ? t.inventory.saving : t.inventory.save}
          </Button>
          <Button type="button" variant="neutral" onClick={onCancel} disabled={saving}>
            {t.inventory.cancel}
          </Button>
        </div>
      </form>

      {error && (
        <p role="alert" className="mt-4 text-lg font-medium text-cancel">
          {error}
        </p>
      )}
    </Card>
  )
}

function BatchesPanel({ product, branchId, onClose }: { product: Product; branchId: number; onClose: () => void }) {
  const [batches, setBatches] = useState<Batch[] | null>(null)
  const [batchNumber, setBatchNumber] = useState('')
  const [initialQuantity, setInitialQuantity] = useState('0')
  const [expirationDate, setExpirationDate] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    listBatchesForProduct(product.id).then(setBatches)
  }

  useEffect(load, [product.id])

  async function handleAddBatch(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createBatch({
        product: product.id,
        branch: branchId,
        batch_number: batchNumber,
        initial_quantity: Number(initialQuantity) || 0,
        expiration_date: expirationDate,
      })
      setBatchNumber('')
      setInitialQuantity('0')
      setExpirationDate('')
      load()
    } catch (err) {
      setError(apiErrorMessage(err, t.inventory.batchErrorGeneric))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-xl font-semibold text-ink">
          {t.inventory.batchesTitle} — {product.name}
        </p>
        <Button type="button" variant="neutral" size="compact" onClick={onClose}>
          {t.inventory.cancel}
        </Button>
      </div>

      {batches === null ? (
        <p className="mt-4 text-lg text-ink/70">{t.inventory.loading}</p>
      ) : batches.length === 0 ? (
        <p className="mt-4 text-lg text-ink/70">{t.inventory.noBatchesYet}</p>
      ) : (
        <ul className="mt-4 flex flex-col gap-2">
          {batches.map((batch) => (
            <li key={batch.id} className="flex items-center justify-between rounded-xl border-2 border-border px-4 py-3">
              <span className="text-lg text-ink">{batch.batch_number}</span>
              <span className="text-lg text-ink/70">
                {t.inventory.currentStock}: {batch.current_quantity} · {formatDate(batch.expiration_date)}
              </span>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={(e) => void handleAddBatch(e)} className="mt-6 flex flex-wrap items-end gap-4">
        <div>
          <Label htmlFor="batch-number">{t.inventory.batchNumber}</Label>
          <Input id="batch-number" required value={batchNumber} onChange={(e) => setBatchNumber(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="batch-initial-quantity">{t.inventory.initialQuantity}</Label>
          <Input
            id="batch-initial-quantity"
            type="number"
            min="0"
            step="1"
            required
            value={initialQuantity}
            onChange={(e) => setInitialQuantity(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="batch-expiration">{t.inventory.expirationDate}</Label>
          <Input
            id="batch-expiration"
            type="date"
            required
            value={expirationDate}
            onChange={(e) => setExpirationDate(e.target.value)}
          />
        </div>
        <Button type="submit" variant="confirm" disabled={saving}>
          {saving ? t.inventory.addingBatch : t.inventory.addBatch}
        </Button>
      </form>

      {error && (
        <p role="alert" className="mt-4 text-lg font-medium text-cancel">
          {error}
        </p>
      )}
    </Card>
  )
}
