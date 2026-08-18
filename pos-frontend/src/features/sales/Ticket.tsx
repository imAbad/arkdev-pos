import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency, formatDateTime } from '@/lib/format'
import { requestSupervisorAuthorization } from '@/services/api/authApi'
import { cancelSale, sendTicketByEmail } from '@/services/api/salesApi'
import { t } from '@/i18n'
import { paymentMethodLabel } from '@/features/sales/payment-labels'
import type { Sale } from '@/types/api'

interface TicketProps {
  sale: Sale
  businessName: string
  changeGiven: number
  onBack: () => void
}

const UNIT_LABEL: Record<string, string> = {
  PIEZA: 'pza',
  KG: 'kg',
  GRAMO: 'g',
  LITRO: 'L',
  PAQUETE: 'paq',
  SERVICIO: '',
}

/** Recibo imprimible de una venta — se llega aquí desde la confirmación
 * ("Ver ticket"), con los datos que ya trae el Sale recién creado (no
 * necesita volver a pedir nada al backend). Imprimir usa el diálogo del
 * navegador (window.print()); solo el recibo es visible al imprimir —
 * los botones de acción se ocultan con la variante `print:hidden` de
 * Tailwind. Integración con impresora térmica queda para el punto 8 del
 * blueprint (hardware real), pospuesto a propósito. */
export function Ticket({ sale: initialSale, businessName, changeGiven, onBack }: TicketProps) {
  const [sale, setSale] = useState(initialSale)
  const [email, setEmail] = useState(initialSale.client_email ?? '')
  const [sendingEmail, setSendingEmail] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [emailSent, setEmailSent] = useState(false)

  async function handleSendEmail() {
    setSendingEmail(true)
    setEmailError(null)
    setEmailSent(false)
    try {
      await sendTicketByEmail(sale.id, email, changeGiven)
      setEmailSent(true)
    } catch (err) {
      setEmailError(apiErrorMessage(err, t.ticket.sendEmailErrorGeneric))
    } finally {
      setSendingEmail(false)
    }
  }

  return (
    <div className="flex min-h-svh flex-col items-center bg-surface-muted p-6 print:bg-white print:p-0">
      <div className="flex w-full max-w-sm justify-between gap-3 print:hidden">
        <Button type="button" variant="neutral" onClick={onBack}>
          {t.ticket.back}
        </Button>
        <Button type="button" variant="confirm" onClick={() => window.print()}>
          {t.ticket.print}
        </Button>
      </div>

      <div className="mt-6 w-full max-w-sm rounded-3xl border-2 border-border bg-white p-6 font-mono text-ink print:mt-0 print:w-full print:max-w-none print:rounded-none print:border-0">
        <div className="text-center">
          <p className="text-xl font-bold">{businessName}</p>
          <p className="mt-1 text-sm">{t.ticket.title}</p>
          <p className="text-sm">
            {t.ticket.date}: {formatDateTime(sale.occurred_at)}
          </p>
        </div>

        <div className="my-4 border-t-2 border-dashed border-border" />

        <ul className="flex flex-col gap-2">
          {sale.details.map((detail) => (
            <li key={detail.id} className="text-sm">
              <p className="font-semibold">{detail.product_name}</p>
              <div className="flex justify-between">
                <span>
                  {detail.quantity} {UNIT_LABEL[detail.product_unit_type] ?? ''} x {formatCurrency(detail.unit_price)}
                </span>
                <span>{formatCurrency(detail.subtotal)}</span>
              </div>
            </li>
          ))}
        </ul>

        <div className="my-4 border-t-2 border-dashed border-border" />

        <div className="flex flex-col gap-1 text-sm">
          <div className="flex justify-between">
            <span>{t.ticket.subtotal}</span>
            <span>{formatCurrency(sale.subtotal)}</span>
          </div>
          <div className="flex justify-between">
            <span>{t.ticket.tax}</span>
            <span>{formatCurrency(sale.tax_amount)}</span>
          </div>
          <div className="flex justify-between text-lg font-bold">
            <span>{t.ticket.total}</span>
            <span>{formatCurrency(sale.total)}</span>
          </div>
        </div>

        <div className="my-4 border-t-2 border-dashed border-border" />

        <div className="flex flex-col gap-1 text-sm">
          <p className="font-semibold">{t.ticket.payments}</p>
          {sale.payments.map((payment) => (
            <div key={payment.id} className="flex justify-between">
              <span>{paymentMethodLabel(payment.method)}</span>
              <span>{formatCurrency(payment.amount)}</span>
            </div>
          ))}
          {changeGiven > 0 && (
            <div className="flex justify-between font-semibold">
              <span>{t.ticket.changeGiven}</span>
              <span>{formatCurrency(changeGiven)}</span>
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 w-full max-w-sm print:hidden">
        <Label htmlFor="ticket-email">{t.ticket.emailLabel}</Label>
        <Input
          id="ticket-email"
          type="email"
          placeholder={t.ticket.emailPlaceholder}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          disabled={sendingEmail}
        />
        <Button
          type="button"
          variant="confirm"
          className="mt-3 w-full"
          onClick={() => void handleSendEmail()}
          disabled={sendingEmail || !email.trim()}
        >
          {sendingEmail ? t.ticket.sendingByEmail : t.ticket.sendByEmail}
        </Button>
        {emailSent && <p className="mt-2 text-lg font-medium text-confirm">{t.ticket.sentByEmail}</p>}
        {emailError && (
          <p role="alert" className="mt-2 text-lg font-medium text-cancel">
            {emailError}
          </p>
        )}
      </div>

      <div className="mt-6 w-full max-w-sm print:hidden">
        <CancelSaleSection sale={sale} onCancelled={setSale} />
      </div>
    </div>
  )
}

/** Punto 10: cancelar/devolver una venta ya cobrada — pide credenciales
 * de un administrador/supervisor (sin tocar la sesión del cajero actual,
 * mismo mecanismo que el resto del sistema para excepciones), obtiene un
 * token de un solo uso y lo consume en un segundo paso. Dos llamadas
 * separadas porque son dos responsabilidades distintas del backend
 * (auth.authorize-exception emite, sales/{id}/cancel consume) — igual
 * que ya está separado del lado del servidor. */
function CancelSaleSection({ sale, onCancelled }: { sale: Sale; onCancelled: (sale: Sale) => void }) {
  const [open, setOpen] = useState(false)
  const [supervisorEmail, setSupervisorEmail] = useState('')
  const [supervisorPassword, setSupervisorPassword] = useState('')
  const [reason, setReason] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [justCancelled, setJustCancelled] = useState(false)

  if (sale.status === 'REFUNDED' || sale.status === 'CANCELLED') {
    return (
      <div>
        <p className="text-lg font-semibold text-cancel">
          {sale.status === 'REFUNDED' ? t.ticket.statusRefunded : t.ticket.statusCancelled}
        </p>
        {justCancelled && <p className="mt-1 text-base text-ink/70">{t.ticket.saleCancelledNotice}</p>}
      </div>
    )
  }

  async function handleConfirm() {
    setCancelling(true)
    setError(null)
    try {
      const authorization = await requestSupervisorAuthorization(supervisorEmail, supervisorPassword, reason)
      const updated = await cancelSale(sale.id, authorization.token)
      onCancelled(updated)
      setJustCancelled(true)
      setOpen(false)
    } catch (err) {
      setError(apiErrorMessage(err, t.ticket.cancelSaleErrorGeneric))
    } finally {
      setCancelling(false)
    }
  }

  if (!open) {
    return (
      <Button type="button" variant="cancel" className="w-full" onClick={() => setOpen(true)}>
        {t.ticket.cancelSale}
      </Button>
    )
  }

  return (
    <div className="rounded-2xl border-2 border-border bg-white p-4">
      <p className="text-lg font-bold text-ink">{t.ticket.cancelSaleTitle}</p>
      <p className="mt-1 text-base text-ink/70">{t.ticket.cancelSaleExplanation}</p>

      <div className="mt-4 flex flex-col gap-3">
        <div>
          <Label htmlFor="cancel-supervisor-email">{t.ticket.supervisorEmail}</Label>
          <Input
            id="cancel-supervisor-email"
            type="email"
            value={supervisorEmail}
            onChange={(e) => setSupervisorEmail(e.target.value)}
            disabled={cancelling}
          />
        </div>
        <div>
          <Label htmlFor="cancel-supervisor-password">{t.ticket.supervisorPassword}</Label>
          <Input
            id="cancel-supervisor-password"
            type="password"
            value={supervisorPassword}
            onChange={(e) => setSupervisorPassword(e.target.value)}
            disabled={cancelling}
          />
        </div>
        <div>
          <Label htmlFor="cancel-reason">{t.ticket.cancelReason}</Label>
          <Input id="cancel-reason" value={reason} onChange={(e) => setReason(e.target.value)} disabled={cancelling} />
        </div>
      </div>

      <div className="mt-4 flex gap-3">
        <Button type="button" variant="neutral" className="flex-1" onClick={() => setOpen(false)} disabled={cancelling}>
          {t.ticket.dismissCancelSale}
        </Button>
        <Button
          type="button"
          variant="cancel"
          className="flex-1"
          onClick={() => void handleConfirm()}
          disabled={cancelling || !supervisorEmail.trim() || !supervisorPassword}
        >
          {cancelling ? t.ticket.cancellingSale : t.ticket.confirmCancelSale}
        </Button>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-lg font-medium text-cancel">
          {error}
        </p>
      )}
    </div>
  )
}
