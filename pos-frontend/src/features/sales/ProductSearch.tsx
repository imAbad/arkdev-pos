import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Input } from '@/components/ui/input'
import { formatCurrency } from '@/lib/format'
import { isNearExpiry } from '@/lib/expiry'
import { searchProducts } from '@/services/api/catalogApi'
import { t } from '@/i18n'
import type { Product } from '@/types/api'

interface ProductSearchProps {
  onSelect: (product: Product) => void
  // Escopa current_stock a esta sucursal (ver services/api/catalogApi.ts)
  // — sin esto, la validación temprana de stock del punto 2 compararía
  // contra existencias de TODAS las sucursales del tenant, no las que de
  // verdad puede vender este turno.
  branchId?: number
}

const SEARCH_DEBOUNCE_MS = 300

export function ProductSearch({ onSelect, branchId }: ProductSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Product[]>([])
  const [searching, setSearching] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      return
    }
    setSearching(true)
    const timeout = setTimeout(() => {
      searchProducts(query, branchId)
        .then(setResults)
        .finally(() => setSearching(false))
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timeout)
  }, [query, branchId])

  function handlePick(product: Product) {
    onSelect(product)
    setQuery('')
    setResults([])
    inputRef.current?.focus()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    // Lector de código de barras: escribe el código y manda Enter — si hay
    // exactamente un resultado, se agrega directo sin que la persona tenga
    // que tocar la pantalla.
    if (event.key === 'Enter' && results.length === 1) {
      event.preventDefault()
      handlePick(results[0])
    }
  }

  return (
    <div>
      <label htmlFor="product-search" className="block text-lg font-medium text-ink mb-2">
        {t.sale.searchLabel}
      </label>
      <Input
        id="product-search"
        ref={inputRef}
        autoFocus
        placeholder={t.sale.searchPlaceholder}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={handleKeyDown}
      />

      {searching && <p className="mt-3 text-lg text-ink/60">{t.sale.searching}</p>}

      {!searching && query.trim() && results.length === 0 && (
        <p role="alert" className="mt-3 text-lg text-ink/60">
          {t.sale.noResults}
        </p>
      )}

      {results.length > 0 && (
        <ul className="mt-3 flex flex-col gap-3">
          {results.map((product) => (
            <li key={product.id}>
              <button
                type="button"
                onClick={() => handlePick(product)}
                className="flex w-full items-center justify-between rounded-2xl border-2 border-border bg-white px-5 py-4 text-left hover:bg-surface-muted"
              >
                <span className="flex items-center gap-3">
                  <span className="text-xl font-medium text-ink">{product.name}</span>
                  {isNearExpiry(product.nearest_batch_expiration) && (
                    <span className="rounded-full border border-warning bg-warning-bg px-3 py-1 text-sm font-semibold text-warning">
                      {t.sale.nearExpiryBadge}
                    </span>
                  )}
                </span>
                <span className="text-xl font-bold text-ink">{formatCurrency(product.sale_price)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
