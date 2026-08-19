import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { daysAgoIso, formatCurrency, formatDate, formatDateTime, todayIso } from '@/lib/format'
import { cn } from '@/lib/utils'
import { t } from '@/i18n'
import { listBranches } from '@/services/api/tenantsApi'
import {
  exportCashShiftClosures,
  exportCashShiftDetail,
  exportExpiredStock,
  exportInventoryAdjustments,
  exportInventoryValuation,
  exportSalesByCashier,
  exportSalesByCategory,
  exportSalesByProduct,
  getCashShiftClosures,
  getCashShiftDetail,
  getExpiredStock,
  getInventoryAdjustments,
  getInventoryValuation,
  getNearExpiryStock,
  getSalesByCashier,
  getSalesByCategory,
  getSalesByProduct,
} from '@/services/api/reportsApi'
import type {
  Branch,
  CashShiftClosureRow,
  CashShiftDetail,
  ExpiredStockRow,
  InventoryAdjustmentReportRow,
  InventoryValuationRow,
  NearExpiryStockRow,
  SalesByCashierRow,
  SalesByCategoryRow,
  SalesByProductRow,
} from '@/types/api'

type ReportKey =
  | 'product' | 'category' | 'cashier' | 'inventory' | 'expired' | 'near-expiry' | 'closures' | 'shift-detail'
  | 'inventory-adjustments'

const TABS: { key: ReportKey; label: string; usesDateRange: boolean; usesDaysWindow?: boolean }[] = [
  { key: 'product', label: t.reports.tabSalesByProduct, usesDateRange: true },
  { key: 'category', label: t.reports.tabSalesByCategory, usesDateRange: true },
  { key: 'cashier', label: t.reports.tabSalesByCashier, usesDateRange: true },
  { key: 'inventory', label: t.reports.tabInventoryValuation, usesDateRange: false },
  { key: 'expired', label: t.reports.tabExpiredStock, usesDateRange: false },
  { key: 'near-expiry', label: t.reports.tabNearExpiry, usesDateRange: false, usesDaysWindow: true },
  { key: 'closures', label: t.reports.tabCashShiftClosures, usesDateRange: true },
  // Drill-down de UN turno de la lista de arriba — mismo filtro de
  // fecha/sucursal para elegirlo, no un reemplazo de "Cierres de caja".
  { key: 'shift-detail', label: t.reports.tabShiftDetail, usesDateRange: true },
  // Observación de sesión (ronda de 4 piezas, punto 4): motivo de cada
  // ajuste manual de stock — aparte de "Mermas por caducidad" (esa es
  // por edad del lote, no una intervención humana con motivo variado).
  { key: 'inventory-adjustments', label: t.reports.tabInventoryAdjustments, usesDateRange: true },
]

type ReportData =
  | { key: 'product'; rows: SalesByProductRow[] }
  | { key: 'category'; rows: SalesByCategoryRow[] }
  | { key: 'cashier'; rows: SalesByCashierRow[] }
  | { key: 'inventory'; rows: InventoryValuationRow[] }
  | { key: 'expired'; rows: ExpiredStockRow[] }
  | { key: 'near-expiry'; rows: NearExpiryStockRow[] }
  | { key: 'closures'; rows: CashShiftClosureRow[] }
  | { key: 'shift-detail'; rows: CashShiftClosureRow[] }
  | { key: 'inventory-adjustments'; rows: InventoryAdjustmentReportRow[] }

export function ReportsScreen() {
  const [activeReport, setActiveReport] = useState<ReportKey>('product')
  const [dateFrom, setDateFrom] = useState(daysAgoIso(30))
  const [dateTo, setDateTo] = useState(todayIso())
  const [branches, setBranches] = useState<Branch[]>([])
  const [branchId, setBranchId] = useState<number | null>(null)
  const [nearExpiryDays, setNearExpiryDays] = useState(7)
  const [data, setData] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  // Sub-estado del tab "shift-detail": null = mostrando la lista de
  // turnos para elegir uno (arriba); con valor = mostrando el detalle
  // completo de ESE turno. No usa `data`/`loading`/`error` de arriba
  // porque conviven — la lista sigue cargada detrás del detalle.
  const [selectedShiftDetail, setSelectedShiftDetail] = useState<CashShiftDetail | null>(null)
  const [shiftDetailLoading, setShiftDetailLoading] = useState(false)
  const [shiftDetailError, setShiftDetailError] = useState<string | null>(null)

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
        case 'shift-detail':
          setData({ key: 'shift-detail', rows: await getCashShiftClosures(filters) })
          break
        case 'inventory-adjustments':
          setData({ key: 'inventory-adjustments', rows: await getInventoryAdjustments(filters) })
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
    'inventory-adjustments': () => exportInventoryAdjustments({ dateFrom, dateTo, branchId }),
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
    setSelectedShiftDetail(null)
    setShiftDetailError(null)
    // Deliberado: solo re-consulta automático al cambiar de pestaña, no
    // en cada tecla de fecha/sucursal (para eso está "Aplicar filtros").
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeReport])

  async function handleViewShiftDetail(shiftId: number) {
    setShiftDetailLoading(true)
    setShiftDetailError(null)
    try {
      setSelectedShiftDetail(await getCashShiftDetail(shiftId))
    } catch (err) {
      setShiftDetailError(apiErrorMessage(err, t.reports.errorGeneric))
    } finally {
      setShiftDetailLoading(false)
    }
  }

  async function handleExportShiftDetail() {
    if (!selectedShiftDetail) return
    setExporting(true)
    setExportError(null)
    try {
      await exportCashShiftDetail(selectedShiftDetail.shift_id)
    } catch (err) {
      setExportError(apiErrorMessage(err, t.reports.exportErrorGeneric))
    } finally {
      setExporting(false)
    }
  }

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

        {!(activeReport === 'shift-detail' && selectedShiftDetail) && (
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
        )}

        {activeReport === 'shift-detail' && (shiftDetailLoading || shiftDetailError || selectedShiftDetail) && (
          <Card>
            {shiftDetailLoading && <p className="text-lg text-ink/70">{t.reports.loading}</p>}
            {shiftDetailError && (
              <p role="alert" className="text-lg font-medium text-cancel">
                {shiftDetailError}
              </p>
            )}
            {!shiftDetailLoading && selectedShiftDetail && (
              <ShiftDetailView
                detail={selectedShiftDetail}
                exporting={exporting}
                onBack={() => setSelectedShiftDetail(null)}
                onExport={() => void handleExportShiftDetail()}
              />
            )}
            {exportError && (
              <p role="alert" className="mt-3 text-lg font-medium text-cancel">
                {exportError}
              </p>
            )}
          </Card>
        )}

        {!(activeReport === 'shift-detail' && selectedShiftDetail) && (
        <Card>
          {loading && <p className="text-lg text-ink/70">{t.reports.loading}</p>}

          {error && (
            <p role="alert" className="text-lg font-medium text-cancel">
              {error}
            </p>
          )}

          {!loading && !error && data && (
            data.key === 'shift-detail'
              ? <ShiftDetailPickerTable rows={data.rows} onViewDetail={(id) => void handleViewShiftDetail(id)} />
              : <ReportTable data={data} />
          )}
        </Card>
        )}
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
    case 'inventory-adjustments':
      return <InventoryAdjustmentsTable rows={data.rows} />
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

function InventoryAdjustmentsTable({ rows }: { rows: InventoryAdjustmentReportRow[] }) {
  return (
    <TableShell
      headers={[
        t.reports.colProduct, t.reports.colBatch, t.reports.colBranch, t.reports.colAdjustment,
        t.reports.colQuantityBefore, t.reports.colQuantityAfter, t.reports.colReason, t.reports.colReasonDetail,
        t.reports.colWho, t.reports.colDateTime,
      ]}
    >
      {rows.map((row) => (
        <tr key={row.id} className="border-b border-border">
          <td className="px-3 py-2">{row.product_name}</td>
          <td className="px-3 py-2">{row.batch_number}</td>
          <td className="px-3 py-2">{row.branch_name}</td>
          <td className={cn('px-3 py-2 font-semibold', row.quantity_delta < 0 ? 'text-cancel' : 'text-confirm')}>
            {row.quantity_delta > 0 ? `+${row.quantity_delta}` : row.quantity_delta}
          </td>
          <td className="px-3 py-2">{row.quantity_before}</td>
          <td className="px-3 py-2">{row.quantity_after}</td>
          <td className="px-3 py-2">{row.reason_label}</td>
          <td className="px-3 py-2">{row.reason_detail || '—'}</td>
          <td className="px-3 py-2">{row.user_email ?? '—'}</td>
          <td className="px-3 py-2">{formatDateTime(row.created_at)}</td>
        </tr>
      ))}
    </TableShell>
  )
}

// Mismos datos que CashShiftClosuresTable (misma consulta, ver runQuery)
// pero con una acción de "Ver detalle" por fila en vez de mostrar todas
// las columnas del arqueo — ese detalle completo es justo lo que
// ShiftDetailView muestra al elegir un turno.
function ShiftDetailPickerTable({ rows, onViewDetail }: { rows: CashShiftClosureRow[]; onViewDetail: (shiftId: number) => void }) {
  if (rows.length === 0) {
    return <p className="text-lg text-ink/70">{t.reports.empty}</p>
  }
  return (
    <TableShell headers={[t.reports.colClosedAt, t.reports.colBranch, t.reports.colRegister, t.reports.colCashier, '']}>
      {rows.map((row) => (
        <tr key={row.id} className="border-b border-border">
          <td className="px-3 py-2">{formatDateTime(row.closed_at)}</td>
          <td className="px-3 py-2">{row.branch_name}</td>
          <td className="px-3 py-2">{row.register_name}</td>
          <td className="px-3 py-2">{row.user_email}</td>
          <td className="px-3 py-2">
            <Button type="button" variant="neutral" size="compact" onClick={() => onViewDetail(row.id)}>
              {t.reports.shiftDetailViewDetail}
            </Button>
          </td>
        </tr>
      ))}
    </TableShell>
  )
}

function ShiftDetailView({
  detail,
  exporting,
  onBack,
  onExport,
}: {
  detail: CashShiftDetail
  exporting: boolean
  onBack: () => void
  onExport: () => void
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Button type="button" variant="neutral" onClick={onBack}>
          {t.reports.shiftDetailBackToList}
        </Button>
        <Button type="button" variant="neutral" disabled={exporting} onClick={onExport}>
          {exporting ? t.reports.exporting : t.reports.exportToExcel}
        </Button>
      </div>

      <div>
        <h2 className="text-2xl font-bold text-ink">{t.reports.shiftDetailSummaryTitle}</h2>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-lg md:grid-cols-3">
          <DetailField label={t.reports.colBranch} value={detail.branch_name} />
          <DetailField label={t.reports.colRegister} value={detail.register_name} />
          <DetailField label={t.reports.colCashier} value={detail.user_email ?? '—'} />
          <DetailField label={t.reports.colClosedAt} value={formatDateTime(detail.closed_at)} />
          <DetailField label={t.reports.colOpeningBalance} value={formatCurrency(detail.opening_balance)} />
          <DetailField label={t.reports.shiftDetailSalesCount} value={String(detail.sales_count)} />
          <DetailField label={t.reports.shiftDetailSalesTotal} value={formatCurrency(detail.sales_total)} />
          <DetailField label={t.reports.colExpectedCash} value={formatCurrency(detail.expected_closing_balance)} />
          <DetailField label={t.reports.colActualCash} value={formatCurrency(detail.actual_closing_balance)} />
          <DetailField
            label={t.reports.colCashDifference}
            value={formatCurrency(detail.cash_difference)}
            emphasize={Number(detail.cash_difference) !== 0}
          />
          <DetailField label={t.reports.colExpectedVoucher} value={formatCurrency(detail.expected_voucher_total)} />
          <DetailField label={t.reports.colActualVoucher} value={formatCurrency(detail.actual_voucher_total)} />
          <DetailField
            label={t.reports.colVoucherDifference}
            value={formatCurrency(detail.voucher_difference)}
            emphasize={Number(detail.voucher_difference) !== 0}
          />
        </dl>
      </div>

      <div>
        <h2 className="text-2xl font-bold text-ink">{t.reports.shiftDetailPaymentsTitle}</h2>
        {detail.payments_by_method.length === 0 ? (
          <p className="mt-2 text-lg text-ink/70">{t.reports.empty}</p>
        ) : (
          <TableShell headers={[t.reports.colMethod, t.reports.colTotal]}>
            {detail.payments_by_method.map((row) => (
              <tr key={row.method} className="border-b border-border">
                <td className="px-3 py-2">{row.method_label}</td>
                <td className="px-3 py-2">{formatCurrency(row.total)}</td>
              </tr>
            ))}
          </TableShell>
        )}
      </div>

      <div>
        <h2 className="text-2xl font-bold text-ink">{t.reports.shiftDetailCreditTitle}</h2>
        <p className="mt-1 text-base text-ink/60">{t.reports.shiftDetailCreditNote}</p>
        {detail.credit_payments.length === 0 ? (
          <p className="mt-2 text-lg text-ink/70">{t.reports.shiftDetailNoCreditPayments}</p>
        ) : (
          <>
            <TableShell headers={[t.reports.colClient, t.reports.colAmount, t.reports.colDateTime]}>
              {detail.credit_payments.map((row) => (
                <tr key={row.id} className="border-b border-border">
                  <td className="px-3 py-2">{row.client_name}</td>
                  <td className="px-3 py-2">{formatCurrency(row.amount)}</td>
                  <td className="px-3 py-2">{formatDateTime(row.created_at)}</td>
                </tr>
              ))}
            </TableShell>
            <p className="mt-4 text-xl font-bold text-ink">
              {t.reports.total}: {formatCurrency(detail.credit_payments_total)}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

function DetailField({ label, value, emphasize = false }: { label: string; value: string; emphasize?: boolean }) {
  return (
    <div>
      <dt className="text-sm font-medium text-ink/60">{label}</dt>
      <dd className={cn('font-semibold text-ink', emphasize && 'text-cancel')}>{value}</dd>
    </div>
  )
}
