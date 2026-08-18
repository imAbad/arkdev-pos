import { t } from '@/i18n'
import type { PaymentMethod } from '@/types/api'

/** Único lugar que traduce un PaymentMethod del backend a texto en
 * español — se reutiliza en PaymentPanel (selector) y Ticket (recibo). */
export function paymentMethodLabel(method: PaymentMethod): string {
  switch (method) {
    case 'CASH':
      return t.sale.methodCash
    case 'CARD':
      return t.sale.methodCard
    case 'TRANSFER':
      return t.sale.methodTransfer
    case 'CREDIT':
      return t.sale.methodCredit
  }
}
