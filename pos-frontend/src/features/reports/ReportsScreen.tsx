import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency, formatDate, formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { t } from '@/i18n'
import { listBranches } from '@/services/api/tenantsApi'
import {
  exportCashShiftClosures,
  exportExpiredStock,
  exportInventoryValuation,
  exportSalesByCashier,
  exportSalesByCategory,
  exportSalesByProduct,
  getCashShiftClosures,
  getExpiredStock,
  getInventoryValuation,
  getNearExpiryStock,
  getSalesByCashier,
  getSalesByCategory,
  getSalesByProduct,
} from '@/services/api/reportsApi'
import type {
  Branch,
  CashShiftClosureRow,
  ExpiredStockRow,
  InventoryValuationRow,
  NearExpiryStockRow,
  SalesByCashierRow,
  SalesByCategoryRow,
  SalesByProductRow,
} from '@/types/api'

type ReportKey = 'product' | 'category' | 'cashier' | 'inventory' | 'expired' | 'near-expiry' | 'closures'

const TABS: { key: ReportKey; label: string; usesDateRange: boolean; usesDaysWindow?: boolean }[] = [
  { key: 'product', label: t.reports.tabSalesByProduct, usesDateRange: true },
  { key: 'category', label: t.reports.tabSalesByCategory, usesDateRange: true },
  { key: 'cashier', label: t.reports.tabSalesByCashier, usesDateRange: true },
  { key: 'inventory', label: t.reports.tabInventoryValuation, usesDateRange: false },
  { key: 'expired', label: t.reports.tabExpiredStock, usesDateRange: false },
  { key: 'near-expiry', label: t.reports.tabNearExpiry, usesDateRange: false, usesDaysWindow: true },
  { key: 'closures', label: t.reports.tabCashShiftClosures, usesDateRange: true },
]

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function thirtyDaysAgoIso(): string {
  const date = new Date()
  date.setDate(date.getDate() - 30)
  return date.toISOString().slice(0, 10)
}

type ReportData =
  | { key: 'product'; rows: SalesByProductRow[] }
  | { key: 'category'; rows: SalesByCategoryRow[] }
  | { key: 'cashier'; rows: SalesByCashierRow[] }
  | { key: 'inventory'; rows: InventoryValuationRow[] }
  | { key: 'expired'; rows: ExpiredStockRow[] }
  | { key: 'near-expiry'; rows: NearExpiryStockRow[] }
  | { key: 'closures'; rows: CashShiftClosureRow[] }

export function ReportsScreen() {
  const [activeReport, setActiveReport] = useState<ReportKey>('product')
  const [dateFrom, setDateFrom] = useState(thirtyDaysAgoIso())
  const [dateTo, setDateTo] = useState(todayIso())
  const [branches, setBranches] = useState<Branch[]>([])
  const [branchId, setBranchId] = useState<number | null>(null)
  const [nearExpiryDays, setNearExpiryDays] = useState(7)
  const [data, setData] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  useEffect(() => {
    listBranches().then(setBranches)
  }, [])

  // Función normal, no useCallback con deps fijos a propósito: así
  // siempre cierra sobre el dateFrom/dateTo/branchId/nearExpiryDays MÁS
  // RECIENTE del render actual (tanto el click de "Aplicar filtros" como
  // el useEffect de abajo la llaman) — con useCallback([activeReport])
  // el botón "Aplicar filtros" habría usado valores de filtro viejos si
  // no se cambiaba de pestaña antes de aplicarlos.
  async function runQuery() {
    setLoading(true)
    setError(null)
    try {
      const filters = { dateFrom, dateTo, branchId }
      switch (activeReport) {
        case 'product':
          setData({ key: 'product', rows: await getSalesByProduct(filters) })
          break
        case 'category':
          setData({ key: 'category', rows: await getSalesByCategory(filters) })
          break
        case 'cashier':
          setData({ key: 'cashier', rows: await getSalesByCashier(filters) })
          break
        case 'inventory':
          setData({ key: 'inventory', rows: await getInventoryValuation({ branchId }) })
          break
        case 'expired':
          setData({ key: 'expired', rows: await getExpiredStock({ branchId }) })
          break
        case 'near-expiry':
          setData({ key: 'near-expiry', rows: await getNearExpiryStock({ branchId, days: nearExpiryDays }) })
          break
        case 'closures':
          setData({ key: 'closures', rows: await getCashShiftClosures(filters) })
          break
      }
    } catch (err) {
      setError(apiErrorMessage(err, t.reports.errorGeneric))
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  // Punto 11: solo "los 4 reportes existentes" antes de esta sesión
  // tienen exportador (product/category/cashier comparten un mismo
  // endpoint, cuentan como uno) — "Próximos a caducar" (punto 4, agregado
  // en esta misma sesión) queda sin botón de exportar a propósito.
  const exporters: Partial<Record<ReportKey, () => Promise<void>>> = {
    product: () => exportSalesByProduct({ dateFrom, dateTo, branchId }),
    category: () => exportSalesByCategory({ dateFrom, dateTo, branchId }),
    cashier: () => exportSalesByCashier({ dateFrom, dateTo, branchId }),
    inventory: () => exportInventoryValuation({ branchId }),
    expired: () => exportExpiredStock({ branchId }),
    closures: () => exportCashShiftClosures({ dateFrom, dateTo, branchId }),
  }

  async function handleExport() {
    const exporter = exporters[activeReport]
    if (!exporter) return
    setExporting(true)
    setExportError(null)
    try {
      await exporter()
    } catch (err) {
      setExportError(apiErrorMessage(err, t.reports.exportErrorGeneric))
    } finally {
      setExporting(false)
    }
  }

  useEffect(() => {
    void runQuery()
    // Deliberado: solo re-consulta automático al cambiar de pestaña, no
    // en cada tecla de fecha/sucursal (para eso está "Aplicar filtros").
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeReport])

  const activeTab = TABS.find((tab) => tab.key === activeReport)!

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <h1 className="text-3xl font-bold text-ink">{t.reports.title}</h1>

      <div className="flex flex-wrap gap-3">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveReport(tab.key)}
              className={cn(
                'rounded-2xl border-2 px-5 py-3 text-lg font-semibold transition-colors',
                activeReport === tab.key
                  ? 'border-accent bg-accent text-white'
                  : 'border-border bg-white text-ink hover:bg-surface-muted',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <Card>
          <div className="flex flex-wrap items-end gap-4">
            {activeTab.usesDateRange && (
              <>
                <div>
                  <Label htmlFor="date-from">{t.reports.dateFrom}</Label>
                  <Input id="date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="date-to">{t.reports.dateTo}</Label>
                  <Input id="date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
                </div>
              </>
            )}

            {activeTab.usesDaysWindow && (
              <div>
                <Label htmlFor="days-window">{t.reports.daysWindow}</Label>
                <Input
                  id="days-window"
                  type="number"
                  min={1}
                  max={365}
                  value={nearExpiryDays}
                  onChange={(e) => setNearExpiryDays(Number(e.target.value) || 7)}
                />
              </div>
            )}

            <div>
              <Label htmlFor="branch-filter">{t.reports.branch}</Label>
              <select
                id="branch-filter"
                className="h-16 rounded-2xl border-2 border-border bg-white px-5 text-xl text-ink"
                value={branchId ?? ''}
                onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">{t.reports.allBranches}</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </div>

            <Button type="button" variant="confirm" onClick={() => void runQuery()}>
              {t.reports.apply}
            </Button>

            {exporters[activeReport] && (
              <Button type="button" variant="neutral" disabled={exporting} onClick={() => void handleExport()}>
                {exporting ? t.reports.exporting : t.reports.exportToExcel}
              </Button>
            )}
          </div>

          {exportError && (
            <p role="alert" className="mt-3 text-lg font-medium text-cancel">
              {exportError}
            </p>
          )}
        </Card>

        <Card>
          {loading && <p className="text-lg text-ink/70">{t.reports.loading}</p>}

          {error && (
            <p role="alert" className="text-lg font-medium text-cancel">
              {error}
            </p>
          )}

          {!loading && !error && data && <ReportTable data={data} />}
        </Card>
    </div>
  )
}

function ReportTable({ data }: { data: ReportData }) {
  if (data.rows.length === 0) {
    return <p className="text-lg text-ink/70">{t.reports.empty}</p>
  }

  switch (data.key) {
    case 'product':
      return <SalesByProductTable rows={data.rows} />
    case 'category':
      return <SalesByCategoryTable rows={data.rows} />
    case 'cashier':
      return <SalesByCashierTable rows={data.rows} />
    case 'inventory':
      return <InventoryValuationTable rows={data.rows} />
    case 'expired':
      return <ExpiredStockTable rows={data.rows} />
    case 'near-expiry':
      return <NearExpiryStockTable rows={data.rows} />
    case 'closures':
      return <CashShiftClosuresTable rows={data.rows} />
  }
}

function TableShell({ headers, children }: { headers: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-max text-left text-lg">
        <thead>
          <tr className="border-b-2 border-border">
            {headers.map((header) => (
              <th key={header} className="whitespace-nowrap px-3 py-2 font-semibold text-ink">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

function SalesByProductTable({ rows }: { rows: SalesByProductRow[] }) {
  return (
    <TableShell headers={[t.reports.colProduct, t.reports.colCategory, t.reports.colQuantitySold, t.reports.colRevenue, t.reports.colTax]}>
      {rows.map((row) => (
        <tr key={row.product_id} className="border-b border-border">
          <td className="px-3 py-2">{row.product_name}</td>
          <td className="px-3 py-2">{row.category_name}</td>
          <td className="px-3 py-2">{row.quantity_sold}</td>
          <td className="px-3 py-2">{formatCurrency(row.revenue)}</td>
          <td className="px-3 py-2">{formatCurrency(row.tax)}</td>
        </tr>
      ))}
    </TableShell>
  )
}

function SalesByCategoryTable({ rows }: { rows: SalesByCategoryRow[] }) {
  return (
    <TableShell headers={[t.reports.colCategory, t.reports.colQuantitySold, t.reports.colRevenue, t.reports.colTax]}>
      {rows.map((row) => (
        <tr key={row.category_id ?? row.category_name} className="border-b border-border">
          <td className="px-3 py-2">{row.category_name}</td>
          <td className="px-3 py-2">{row.quantity_sold}</td>
          <td className="px-3 py-2">{formatCurrency(row.revenue)}</td>
          <td className="px-3 py-2">{formatCurrency(row.tax)}</td>
        </tr>
      ))}
    </TableShell>
  )
}

function SalesByCashierTable({ rows }: { rows: SalesByCashierRow[] }) {
  return (
    <TableShell headers={[t.reports.colCashier, t.reports.colQuantitySold, t.reports.colRevenue, t.reports.colTax]}>
      {rows.map((row) => (
        <tr key={row.cashier_id} className="border-b border-border">
          <td className="px-3 py-2">{row.cashier_email}</td>
          <td className="px-3 py-2">{row.quantity_sold}</td>
          <td className="px-3 py-2">{formatCurrency(row.revenue)}</td>
          <td className="px-3 py-2">{formatCurrency(row.tax)}</td>
        </tr>
      ))}
    </TableShell>
  )
}

function InventoryValuationTable({ rows }: { rows: InventoryValuationRow[] }) {
  const total = rows.reduce((sum, row) => sum + Number(row.valuation), 0)
  return (
    <>
      <TableShell headers={[t.reports.colProduct, t.reports.colCategory, t.reports.colQuantity, t.reports.colValuation]}>
        {rows.map((row) => (
          <tr key={row.product_id} className="border-b border-border">
            <td className="px-3 py-2">{row.product_name}</td>
            <td className="px-3 py-2">{row.category_name}</td>
            <td className="px-3 py-2">{row.quantity}</td>
            <td className="px-3 py-2">{formatCurrency(row.valuation)}</td>
          </tr>
        ))}
      </TableShell>
      <p className="mt-4 text-xl font-bold text-ink">
        {t.reports.total}: {formatCurrency(total)}
      </p>
    </>
  )
}

function ExpiredStockTable({ rows }: { rows: ExpiredStockRow[] }) {
  const total = rows.reduce((sum, row) => sum + Number(row.valuation), 0)
  return (
    <>
      <p className="mb-4 text-lg text-ink/70">{t.reports.expiredStockNote}</p>
      <TableShell
        headers={[
          t.reports.colProduct,
          t.reports.colBatch,
          t.reports.colBranch,
          t.reports.colExpirationDate,
          t.reports.colQuantity,
          t.reports.colValuation,
        ]}
      >
        {rows.map((row) => (
          <tr key={row.batch_id} className="border-b border-border">
            <td className="px-3 py-2">{row.product_name}</td>
            <td className="px-3 py-2">{row.batch_number}</td>
            <td className="px-3 py-2">{row.branch_name}</td>
            <td className="px-3 py-2">{formatDate(row.expiration_date)}</td>
            <td className="px-3 py-2">{row.quantity}</td>
            <td className="px-3 py-2">{formatCurrency(row.valuation)}</td>
          </tr>
        ))}
      </TableShell>
      <p className="mt-4 text-xl font-bold text-ink">
        {t.reports.total}: {formatCurrency(total)}
      </p>
    </>
  )
}

function NearExpiryStockTable({ rows }: { rows: NearExpiryStockRow[] }) {
  const total = rows.reduce((sum, row) => sum + Number(row.valuation), 0)
  return (
    <>
      <p className="mb-4 text-lg text-ink/70">{t.reports.nearExpiryNote}</p>
      <TableShell
        headers={[
          t.reports.colProduct,
          t.reports.colBatch,
          t.reports.colBranch,
          t.reports.colExpirationDate,
          t.reports.colDaysToExpire,
          t.reports.colQuantity,
          t.reports.colValuation,
        ]}
      >
        {rows.map((row) => (
          <tr key={row.batch_id} className="border-b border-border">
            <td className="px-3 py-2">{row.product_name}</td>
            <td className="px-3 py-2">{row.batch_number}</td>
            <td className="px-3 py-2">{row.branch_name}</td>
            <td className="px-3 py-2">{formatDate(row.expiration_date)}</td>
            <td className="px-3 py-2 font-semibold text-warning">{row.days_to_expire}</td>
            <td className="px-3 py-2">{row.quantity}</td>
            <td className="px-3 py-2">{formatCurrency(row.valuation)}</td>
          </tr>
        ))}
      </TableShell>
      <p className="mt-4 text-xl font-bold text-ink">
        {t.reports.total}: {formatCurrency(total)}
      </p>
    </>
  )
}

function CashShiftClosuresTable({ rows }: { rows: CashShiftClosureRow[] }) {
  return (
    <TableShell
      headers={[
        t.reports.colClosedAt,
        t.reports.colBranch,
        t.reports.colRegister,
        t.reports.colCashier,
        t.reports.colOpeningBalance,
        t.reports.colExpectedCash,
        t.reports.colActualCash,
        t.reports.colCashDifference,
        t.reports.colExpectedVoucher,
        t.reports.colActualVoucher,
        t.reports.colVoucherDifference,
      ]}
    >
      {rows.map((row) => (
        <tr key={row.id} className="border-b border-border">
          <td className="px-3 py-2">{formatDateTime(row.closed_at)}</td>
          <td className="px-3 py-2">{row.branch_name}</td>
          <td className="px-3 py-2">{row.register_name}</td>
          <td className="px-3 py-2">{row.user_email}</td>
          <td className="px-3 py-2">{formatCurrency(row.opening_balance)}</td>
          <td className="px-3 py-2">{formatCurrency(row.expected_closing_balance)}</td>
          <td className="px-3 py-2">{formatCurrency(row.actual_closing_balance)}</td>
          <td className={cn('px-3 py-2 font-semibold', Number(row.cash_difference) === 0 ? 'text-confirm' : 'text-cancel')}>
            {formatCurrency(row.cash_difference)}
          </td>
          <td className="px-3 py-2">{formatCurrency(row.expected_voucher_total)}</td>
          <td className="px-3 py-2">{formatCurrency(row.actual_voucher_total)}</td>
          <td className={cn('px-3 py-2 font-semibold', Number(row.voucher_difference) === 0 ? 'text-confirm' : 'text-cancel')}>
            {formatCurrency(row.voucher_difference)}
          </td>
        </tr>
      ))}
    </TableShell>
  )
}
