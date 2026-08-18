import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/format'
import { isNearExpiry } from '@/lib/expiry'
import { t } from '@/i18n'
import { allowsFractionalQuantity, lineTotal, type CartLine } from '@/features/sales/cart'

interface CartViewProps {
  lines: CartLine[]
  onChangeQuantity: (productId: number, quantity: number) => void
  onRemove: (productId: number) => void
}

export function CartView({ lines, onChangeQuantity, onRemove }: CartViewProps) {
  if (lines.length === 0) {
    return <p className="text-lg text-ink/60">{t.sale.emptyCart}</p>
  }

  return (
    <ul className="flex flex-col gap-3">
      {lines.map((line) => {
        const step = allowsFractionalQuantity(line.product) ? 0.1 : 1
        const min = step
        return (
          <li
            key={line.product.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border-2 border-border bg-white px-5 py-4"
          >
            <div className="min-w-40 flex-1">
              <p className="flex items-center gap-2 text-xl font-medium text-ink">
                {line.product.name}
                {isNearExpiry(line.product.nearest_batch_expiration) && (
                  <span className="rounded-full border border-warning bg-warning-bg px-3 py-1 text-sm font-semibold text-warning">
                    {t.sale.nearExpiryBadge}
                  </span>
                )}
              </p>
              <p className="text-lg text-ink/60">{formatCurrency(line.product.sale_price)} c/u</p>
            </div>

            <div className="flex items-center gap-2">
              <label className="sr-only" htmlFor={`quantity-${line.product.id}`}>
                {t.sale.quantity}
              </label>
              <input
                id={`quantity-${line.product.id}`}
                type="number"
                min={min}
                step={step}
                value={line.quantity}
                onChange={(event) => {
                  // Sin bloquear en 0/vacío mientras se escribe: si el
                  // input se queda en 0 o vacío al perder el foco (onBlur),
                  // ahí sí se corrige a 1 — bloquearlo aquí (value > 0)
                  // rompía el gesto normal de "borrar y volver a escribir"
                  // (el input quedaba pegado en el valor anterior).
                  const raw = event.target.value
                  onChangeQuantity(line.product.id, raw === '' ? 0 : Number(raw))
                }}
                onBlur={(event) => {
                  const value = Number(event.target.value)
                  if (!(value > 0)) onChangeQuantity(line.product.id, 1)
                }}
                className="h-14 w-24 rounded-xl border-2 border-border text-center text-xl text-ink"
              />
            </div>

            <p className="w-28 text-right text-xl font-bold text-ink">{formatCurrency(lineTotal(line))}</p>

            <Button
              type="button"
              variant="cancel"
              size="compact"
              onClick={() => onRemove(line.product.id)}
              aria-label={`${t.sale.remove} ${line.product.name}`}
            >
              {t.sale.remove}
            </Button>
          </li>
        )
      })}
    </ul>
  )
}
