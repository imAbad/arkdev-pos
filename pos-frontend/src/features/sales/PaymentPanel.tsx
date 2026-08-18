import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatCurrency } from '@/lib/format'
import { t } from '@/i18n'
import { cn } from '@/lib/utils'
import { paymentMethodLabel } from '@/features/sales/payment-labels'
import type { PaymentMethod } from '@/types/api'

// Fiado (CREDIT) queda fuera de esta pantalla a propósito: requiere elegir
// un cliente (customers.Client), fuera del alcance de esta sesión — ver
// arquitectura_tecnica_pos.md.
const METHODS: PaymentMethod[] = ['CASH', 'CARD', 'TRANSFER']

interface PaymentPanelProps {
  total: number
  method: PaymentMethod
  onChangeMethod: (method: PaymentMethod) => void
  cashReceived: string
  onChangeCashReceived: (value: string) => void
  reference: string
  onChangeReference: (value: string) => void
  onCharge: () => void
  submitting: boolean
  disabled: boolean
}

export function PaymentPanel({
  total,
  method,
  onChangeMethod,
  cashReceived,
  onChangeCashReceived,
  reference,
  onChangeReference,
  onCharge,
  submitting,
  disabled,
}: PaymentPanelProps) {
  const receivedAmount = Number(cashReceived) || 0
  const change = method === 'CASH' ? receivedAmount - total : 0
  const cashInsufficient = method === 'CASH' && receivedAmount < total
  const canCharge = !disabled && !submitting && !cashInsufficient

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-lg font-medium text-ink mb-2">{t.sale.paymentMethod}</p>
        <div className="grid grid-cols-3 gap-3">
          {METHODS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => onChangeMethod(value)}
              className={cn(
                'flex h-16 items-center justify-center rounded-2xl border-2 text-lg font-semibold transition-colors',
                method === value
                  ? 'border-accent bg-accent text-white'
                  : 'border-border bg-white text-ink hover:bg-surface-muted',
              )}
            >
              {paymentMethodLabel(value)}
            </button>
          ))}
        </div>
      </div>

      {(method === 'CARD' || method === 'TRANSFER') && (
        <div>
          <Label htmlFor="payment-reference">{t.sale.referenceLabel}</Label>
          <Input
            id="payment-reference"
            type="text"
            maxLength={20}
            placeholder={t.sale.referencePlaceholder}
            value={reference}
            onChange={(event) => onChangeReference(event.target.value)}
          />
        </div>
      )}

      {method === 'CASH' && (
        <div>
          <Label htmlFor="cash-received">{t.sale.cashReceived}</Label>
          <Input
            id="cash-received"
            type="number"
            min="0"
            step="0.01"
            inputMode="decimal"
            value={cashReceived}
            onChange={(event) => onChangeCashReceived(event.target.value)}
          />
          {cashInsufficient ? (
            <p role="alert" className="mt-2 text-lg font-medium text-cancel">
              {t.sale.changeInsufficient}
            </p>
          ) : (
            <p className="mt-2 text-lg text-ink">
              {t.sale.change}: <span className="font-bold">{formatCurrency(change)}</span>
            </p>
          )}
        </div>
      )}

      <div className="flex items-baseline justify-between border-t-2 border-border pt-4">
        <span className="text-2xl font-semibold text-ink">{t.sale.total}</span>
        <span className="text-4xl font-extrabold text-ink">{formatCurrency(total)}</span>
      </div>

      <Button type="button" variant="confirm" size="large" onClick={onCharge} disabled={!canCharge}>
        {submitting ? t.sale.chargeSubmitting : t.sale.charge}
      </Button>
    </div>
  )
}
