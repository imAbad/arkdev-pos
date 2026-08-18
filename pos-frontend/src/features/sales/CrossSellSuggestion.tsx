import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/format'
import { t } from '@/i18n'
import type { RelatedProductSummary } from '@/types/api'

interface CrossSellSuggestionProps {
  items: RelatedProductSummary[]
  onAdd: (id: number) => void
  onDismiss: () => void
}

/** Visible pero nunca bloqueante — sin popup/modal, se puede ignorar sin
 * cerrar nada. Configurado a mano por el administrador (Product.
 * related_products), no automático ni basado en historial de compra
 * (sobre-ingeniería fuera de alcance para este tamaño de negocio). */
export function CrossSellSuggestion({ items, onAdd, onDismiss }: CrossSellSuggestionProps) {
  if (items.length === 0) return null

  return (
    <div className="mt-4 rounded-2xl border-2 border-border bg-surface-muted p-4">
      <div className="flex items-center justify-between">
        <p className="text-lg font-semibold text-ink">{t.sale.crossSellTitle}</p>
        <button type="button" onClick={onDismiss} aria-label={t.sale.crossSellDismiss} className="text-lg text-ink/50 hover:text-ink">
          ✕
        </button>
      </div>
      <ul className="mt-3 flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.id} className="flex items-center justify-between gap-3 rounded-xl bg-white px-4 py-3">
            <span className="text-lg text-ink">{item.name}</span>
            <div className="flex items-center gap-3">
              <span className="text-lg font-semibold text-ink">{formatCurrency(item.sale_price)}</span>
              <Button type="button" variant="confirm" size="compact" onClick={() => onAdd(item.id)}>
                {t.sale.crossSellAdd}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
