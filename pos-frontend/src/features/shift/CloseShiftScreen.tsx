import { useState } from 'react'
import { AppHeader } from '@/components/app-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency } from '@/lib/format'
import { closeShift } from '@/services/api/salesApi'
import { t } from '@/i18n'
import { cn } from '@/lib/utils'
import { useAuth } from '@/features/auth/AuthProvider'
import type { CashShift } from '@/types/api'

interface CloseShiftScreenProps {
  shift: CashShift
  onCancel: () => void
  /** Cuando se provee, el resultado ofrece un botón extra además de
   * "Cerrar sesión" — caso de uso: admin/supervisor cerró el turno
   * ajeno de una caja varada (punto 0) y quiere volver a "Abrir turno"
   * en vez de forzosamente cerrar sesión. Si se omite (uso normal desde
   * SaleScreen, cerrando el propio turno), el resultado se comporta
   * igual que antes — un único botón. */
  onClosed?: () => void
}

/** Arqueo ciego por diseño: el cajero declara actual_* sin ver expected_*
 * primero — el backend solo revela expected_* en la respuesta DESPUÉS de
 * recibir lo declarado (ver services.close_shift). No mostrar el
 * expected_* antes de enviar, ni siquiera en un cálculo local. */
export function CloseShiftScreen({ shift, onCancel, onClosed }: CloseShiftScreenProps) {
  const { logout } = useAuth()
  const [actualCash, setActualCash] = useState('0')
  const [actualVoucher, setActualVoucher] = useState('0')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<CashShift | null>(null)

  async function handleSubmit() {
    setSubmitting(true)
    setError(null)
    try {
      const closed = await closeShift(shift.id, actualCash, actualVoucher)
      setResult(closed)
    } catch (err) {
      setError(apiErrorMessage(err, t.closeShift.errorGeneric))
    } finally {
      setSubmitting(false)
    }
  }

  if (result) {
    return (
      <div className="flex min-h-svh flex-col bg-surface-muted">
        <AppHeader />
        <div className="flex flex-1 items-center justify-center p-6">
          <Card className="w-full max-w-md">
            <h1 className="text-3xl font-bold text-ink">{t.closeShift.resultTitle}</h1>

            <DifferenceSection
              title={t.closeShift.cashSectionTitle}
              expected={result.expected_closing_balance}
              actual={result.actual_closing_balance}
              difference={result.cash_difference}
            />
            <DifferenceSection
              title={t.closeShift.voucherSectionTitle}
              expected={result.expected_voucher_total}
              actual={result.actual_voucher_total}
              difference={result.voucher_difference}
            />

            {onClosed && (
              <Button variant="confirm" size="large" className="mt-8 w-full" onClick={onClosed}>
                {t.closeShift.continueNext}
              </Button>
            )}
            <Button variant="neutral" size="large" className={cn('w-full', onClosed ? 'mt-4' : 'mt-8')} onClick={logout}>
              {t.closeShift.logoutNext}
            </Button>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      <AppHeader />
      <div className="flex flex-1 items-center justify-center p-6">
        <Card className="w-full max-w-md">
          <h1 className="text-3xl font-bold text-ink">{t.closeShift.formTitle}</h1>
          <p className="mt-2 text-lg text-ink/70">{t.closeShift.formSubtitle}</p>

          <div className="mt-8 flex flex-col gap-6">
            <div>
              <Label htmlFor="actual-cash">{t.closeShift.actualCash}</Label>
              <Input
                id="actual-cash"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={actualCash}
                onChange={(event) => setActualCash(event.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="actual-voucher">{t.closeShift.actualVoucher}</Label>
              <Input
                id="actual-voucher"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={actualVoucher}
                onChange={(event) => setActualVoucher(event.target.value)}
              />
            </div>

            {error && (
              <p role="alert" className="text-lg font-medium text-cancel">
                {error}
              </p>
            )}

            <Button type="button" variant="confirm" size="large" onClick={handleSubmit} disabled={submitting}>
              {submitting ? t.closeShift.submitting : t.closeShift.submit}
            </Button>
            <Button type="button" variant="neutral" onClick={onCancel} disabled={submitting}>
              {t.closeShift.cancel}
            </Button>
          </div>
        </Card>
      </div>
    </div>
  )
}

function DifferenceSection({
  title,
  expected,
  actual,
  difference,
}: {
  title: string
  expected: string | null
  actual: string | null
  difference: string | null
}) {
  const diffValue = Number(difference ?? '0')
  const matches = diffValue === 0
  const statusLabel = matches ? t.closeShift.matches : diffValue > 0 ? t.closeShift.surplus : t.closeShift.shortage

  return (
    <div className="mt-6 rounded-2xl border-2 border-border p-5">
      <p className="text-lg font-semibold text-ink">{title}</p>
      <div className="mt-3 flex justify-between text-lg text-ink/70">
        <span>{t.closeShift.expected}</span>
        <span>{formatCurrency(expected ?? '0')}</span>
      </div>
      <div className="mt-1 flex justify-between text-lg text-ink/70">
        <span>{t.closeShift.counted}</span>
        <span>{formatCurrency(actual ?? '0')}</span>
      </div>
      <div
        className={cn(
          'mt-3 flex items-center justify-between rounded-xl px-4 py-3 text-xl font-bold text-white',
          matches ? 'bg-confirm' : 'bg-cancel',
        )}
      >
        <span>{statusLabel}</span>
        <span>{formatCurrency(difference ?? '0')}</span>
      </div>
    </div>
  )
}
