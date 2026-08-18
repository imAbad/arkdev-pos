import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/format'
import { t } from '@/i18n'
import type { Sale } from '@/types/api'

interface SaleConfirmationProps {
  sale: Sale
  changeGiven: number
  onNewSale: () => void
  onViewTicket: () => void
}

/** Pantalla completa, no un toast — la confirmación de que se cobró bien
 * es lo más importante que la persona necesita ver en todo el flujo. */
export function SaleConfirmation({ sale, changeGiven, onNewSale, onViewTicket }: SaleConfirmationProps) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-8 bg-confirm p-6 text-center text-white">
      <div className="flex h-28 w-28 items-center justify-center rounded-full bg-white/20 text-6xl">✓</div>
      <h1 className="text-5xl font-extrabold">{t.confirmation.title}</h1>

      <div className="w-full max-w-sm rounded-3xl bg-white/10 p-8">
        <p className="text-xl">{t.confirmation.totalCharged}</p>
        <p className="text-5xl font-extrabold">{formatCurrency(sale.total)}</p>

        {changeGiven > 0 && (
          <>
            <p className="mt-6 text-xl">{t.confirmation.changeGiven}</p>
            <p className="text-4xl font-extrabold">{formatCurrency(changeGiven)}</p>
          </>
        )}
      </div>

      <div className="flex w-full max-w-sm flex-col gap-4">
        <Button variant="neutral" size="large" onClick={onViewTicket}>
          {t.confirmation.viewTicket}
        </Button>
        <Button variant="neutral" size="large" onClick={onNewSale}>
          {t.confirmation.newSale}
        </Button>
      </div>
    </div>
  )
}
