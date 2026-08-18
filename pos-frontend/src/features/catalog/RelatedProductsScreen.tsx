import { useEffect, useState } from 'react'
import { AppHeader } from '@/components/app-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency } from '@/lib/format'
import { searchProducts, updateProductRelatedProducts } from '@/services/api/catalogApi'
import { useNavigation } from '@/App'
import { t } from '@/i18n'
import type { Product } from '@/types/api'

const SEARCH_DEBOUNCE_MS = 300

/** Mismo patrón de búsqueda con debounce que ProductSearch.tsx — sin
 * esto, tipear rápido dispara una request por tecla y, al no cancelarse
 * las anteriores, una respuesta vieja puede llegar DESPUÉS que la de la
 * query actual y pisarla con resultados de una búsqueda más corta/amplia
 * (bug real encontrado probando "frijol" a mano: "f" solo ya hace match
 * con "Refresco", "Café", etc., y esa respuesta llegaba tarde). */
function useDebouncedProductSearch(query: string): Product[] {
  const [results, setResults] = useState<Product[]>([])

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      return
    }
    const timeout = setTimeout(() => {
      searchProducts(query).then(setResults)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timeout)
  }, [query])

  return results
}

/** Punto 5, versión simple a propósito: no hay pantalla de edición de
 * producto todavía (eso es el punto 8) — esta pantalla standalone solo
 * configura related_products, sin tocar nombre/precio/catálogo. Cuando
 * el punto 8 construya la edición completa de producto, esto puede
 * integrarse ahí; mientras tanto ya cierra el punto 5 por sí sola. */
export function RelatedProductsScreen() {
  const { closeCatalog } = useNavigation()
  const [sourceQuery, setSourceQuery] = useState('')
  const sourceResults = useDebouncedProductSearch(sourceQuery)
  const [source, setSource] = useState<Product | null>(null)

  const [addQuery, setAddQuery] = useState('')
  const addResults = useDebouncedProductSearch(addQuery)

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function pickSource(product: Product) {
    setSource(product)
    setSourceQuery('')
    setAddQuery('')
    setError(null)
  }

  async function saveRelated(nextIds: number[]) {
    if (source === null) return
    setSaving(true)
    setError(null)
    try {
      const updated = await updateProductRelatedProducts(source.id, nextIds)
      setSource(updated)
    } catch (err) {
      setError(apiErrorMessage(err, t.relatedProducts.errorGeneric))
    } finally {
      setSaving(false)
    }
  }

  function addRelated(product: Product) {
    if (source === null) return
    const nextIds = [...source.related_products, product.id]
    setAddQuery('')
    void saveRelated(nextIds)
  }

  function removeRelated(productId: number) {
    if (source === null) return
    void saveRelated(source.related_products.filter((id) => id !== productId))
  }

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      <AppHeader />

      <div className="flex flex-1 flex-col gap-6 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-ink">{t.relatedProducts.title}</h1>
            <p className="mt-2 text-lg text-ink/70">{t.relatedProducts.subtitle}</p>
          </div>
          <Button type="button" variant="neutral" onClick={closeCatalog}>
            {t.relatedProducts.back}
          </Button>
        </div>

        <Card>
          <Label htmlFor="source-search">{t.relatedProducts.chooseProduct}</Label>
          <Input
            id="source-search"
            placeholder={t.sale.searchPlaceholder}
            value={sourceQuery}
            onChange={(event) => setSourceQuery(event.target.value)}
          />
          {sourceResults.length > 0 && (
            <ul className="mt-3 flex flex-col gap-2">
              {sourceResults.map((product) => (
                <li key={product.id}>
                  <button
                    type="button"
                    onClick={() => pickSource(product)}
                    className="flex w-full items-center justify-between rounded-xl border-2 border-border bg-white px-4 py-3 text-left hover:bg-surface-muted"
                  >
                    <span className="text-lg text-ink">{product.name}</span>
                    <span className="text-lg font-semibold text-ink">{formatCurrency(product.sale_price)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {source && (
          <Card>
            <p className="text-xl font-semibold text-ink">{source.name}</p>

            <p className="mt-4 text-lg font-medium text-ink">{t.relatedProducts.currentlyRelated}</p>
            {source.related_products_detail.length === 0 ? (
              <p className="mt-2 text-lg text-ink/60">{t.relatedProducts.noneYet}</p>
            ) : (
              <ul className="mt-2 flex flex-col gap-2">
                {source.related_products_detail.map((related) => (
                  <li
                    key={related.id}
                    className="flex items-center justify-between gap-3 rounded-xl border-2 border-border bg-white px-4 py-3"
                  >
                    <span className="text-lg text-ink">{related.name}</span>
                    <Button
                      type="button"
                      variant="cancel"
                      size="compact"
                      disabled={saving}
                      onClick={() => removeRelated(related.id)}
                    >
                      {t.relatedProducts.remove}
                    </Button>
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-6">
              <Label htmlFor="add-related-search">{t.relatedProducts.addRelated}</Label>
              <Input
                id="add-related-search"
                placeholder={t.sale.searchPlaceholder}
                value={addQuery}
                onChange={(event) => setAddQuery(event.target.value)}
                disabled={saving}
              />
              {addResults.length > 0 && (
                <ul className="mt-3 flex flex-col gap-2">
                  {addResults
                    .filter((product) => product.id !== source.id && !source.related_products.includes(product.id))
                    .map((product) => (
                      <li key={product.id}>
                        <button
                          type="button"
                          onClick={() => addRelated(product)}
                          className="flex w-full items-center justify-between rounded-xl border-2 border-border bg-white px-4 py-3 text-left hover:bg-surface-muted"
                        >
                          <span className="text-lg text-ink">{product.name}</span>
                          <span className="text-lg font-semibold text-confirm">{t.relatedProducts.add}</span>
                        </button>
                      </li>
                    ))}
                </ul>
              )}
            </div>

            {error && (
              <p role="alert" className="mt-4 text-lg font-medium text-cancel">
                {error}
              </p>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}
