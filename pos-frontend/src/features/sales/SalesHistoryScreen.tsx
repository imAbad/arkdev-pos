import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { daysAgoIso, formatCurrency, formatDateTime, todayIso } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuth } from '@/features/auth/AuthProvider'
import { listSales } from '@/services/api/salesApi'
import { Ticket } from '@/features/sales/Ticket'
import { t } from '@/i18n'
import type { Sale, SaleStatus } from '@/types/api'

const STATUS_LABEL: Record<SaleStatus, string> = {
  COMPLETED: t.salesHistory.statusCompleted,
  REFUNDED: t.salesHistory.statusRefunded,
  CANCELLED: t.salesHistory.statusCancelled,
}

const STATUS_TONE: Record<SaleStatus, string> = {
  COMPLETED: 'text-confirm',
  REFUNDED: 'text-cancel',
  CANCELLED: 'text-cancel',
}

/** Observación de sesión, punto 2: historial de ventas navegable — antes
 * de esto, el ticket de una venta (con cancelar/reenviar del punto 10)
 * solo era alcanzable en el momento de cobrarla, dentro del mismo flujo.
 * Reutiliza Ticket.tsx tal cual (ya trae cancelar/imprimir/enviar por
 * correo) — este es solo el punto de entrada para llegar a un ticket
 * viejo. */
export function SalesHistoryScreen() {
  const { companySettings } = useAuth()
  const [dateFrom, setDateFrom] = useState(daysAgoIso(30))
  const [dateTo, setDateTo] = useState(todayIso())
  const [sales, setSales] = useState<Sale[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Sale | null>(null)

  async function runQuery() {
    setLoading(true)
    setError(null)
    try {
      setSales(await listSales(dateFrom, dateTo))
    } catch (err) {
      setError(apiErrorMessage(err, t.salesHistory.errorGeneric))
      setSales(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void runQuery()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (selected) {
    const businessName = companySettings?.business_name?.trim() || t.common.appName
    return (
      <Ticket
        sale={selected}
        businessName={businessName}
        logoUrl={companySettings?.logo}
        changeGiven={0}
        onBack={() => {
          setSelected(null)
          void runQuery()
        }}
      />
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold text-ink">{t.salesHistory.title}</h1>
        <p className="mt-2 text-lg text-ink/70">{t.salesHistory.subtitle}</p>
      </div>

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <Label htmlFor="sales-history-date-from">{t.salesHistory.dateFrom}</Label>
            <Input id="sales-history-date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="sales-history-date-to">{t.salesHistory.dateTo}</Label>
            <Input id="sales-history-date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <Button type="button" variant="confirm" onClick={() => void runQuery()}>
            {t.salesHistory.apply}
          </Button>
        </div>
      </Card>

      <Card>
        {loading && <p className="text-lg text-ink/70">{t.salesHistory.loading}</p>}

        {error && (
          <p role="alert" className="text-lg font-medium text-cancel">
            {error}
          </p>
        )}

        {!loading && !error && sales !== null && sales.length === 0 && (
          <p className="text-lg text-ink/70">{t.salesHistory.empty}</p>
        )}

        {!loading && !error && sales !== null && sales.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-max text-left text-lg">
              <thead>
                <tr className="border-b-2 border-border">
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.salesHistory.colDate}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.salesHistory.colCashier}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.salesHistory.colTotal}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.salesHistory.colStatus}</th>
                </tr>
              </thead>
              <tbody>
                {sales.map((sale) => (
                  <tr
                    key={sale.id}
                    onClick={() => setSelected(sale)}
                    className="cursor-pointer border-b border-border hover:bg-surface-muted"
                  >
                    <td className="px-3 py-2">{formatDateTime(sale.occurred_at)}</td>
                    <td className="px-3 py-2">{sale.cashier_email}</td>
                    <td className="px-3 py-2 font-semibold">{formatCurrency(sale.total)}</td>
                    <td className={cn('px-3 py-2 font-semibold', STATUS_TONE[sale.status])}>
                      {STATUS_LABEL[sale.status]}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
