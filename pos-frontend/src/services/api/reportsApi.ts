import { apiClient } from '@/lib/api-client'
import type {
  CashShiftClosureRow,
  CashShiftDetail,
  ExpiredStockRow,
  InventoryValuationRow,
  NearExpiryStockRow,
  SalesByCashierRow,
  SalesByCategoryRow,
  SalesByProductRow,
} from '@/types/api'

export interface DateRangeReportFilters {
  dateFrom: string
  dateTo: string
  branchId?: number | null
}

export interface BranchOnlyReportFilters {
  branchId?: number | null
}

function branchParam(branchId?: number | null) {
  return branchId ? { branch: branchId } : {}
}

/** Punto 11: dispara la descarga real del archivo en el navegador —
 * `export=xlsx` (no `format=xlsx`: DRF reserva ese nombre para su propia
 * negociación de contenido y devuelve 404 antes de llegar a la vista, ver
 * reports/views.py del backend). `responseType: 'blob'` porque axios no
 * debe intentar parsear la respuesta como JSON. */
async function downloadExcel(url: string, params: Record<string, unknown>, filename: string): Promise<void> {
  const response = await apiClient.get<Blob>(url, { params: { ...params, export: 'xlsx' }, responseType: 'blob' })
  const blobUrl = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = filename
  link.click()
  URL.revokeObjectURL(blobUrl)
}

export async function getSalesByProduct(filters: DateRangeReportFilters): Promise<SalesByProductRow[]> {
  const response = await apiClient.get<SalesByProductRow[]>('/reports/sales-by-product/', {
    params: { date_from: filters.dateFrom, date_to: filters.dateTo, group_by: 'product', ...branchParam(filters.branchId) },
  })
  return response.data
}

export async function getSalesByCategory(filters: DateRangeReportFilters): Promise<SalesByCategoryRow[]> {
  const response = await apiClient.get<SalesByCategoryRow[]>('/reports/sales-by-product/', {
    params: { date_from: filters.dateFrom, date_to: filters.dateTo, group_by: 'category', ...branchParam(filters.branchId) },
  })
  return response.data
}

export async function getSalesByCashier(filters: DateRangeReportFilters): Promise<SalesByCashierRow[]> {
  const response = await apiClient.get<SalesByCashierRow[]>('/reports/sales-by-product/', {
    params: { date_from: filters.dateFrom, date_to: filters.dateTo, group_by: 'cashier', ...branchParam(filters.branchId) },
  })
  return response.data
}

export async function getInventoryValuation(filters: BranchOnlyReportFilters): Promise<InventoryValuationRow[]> {
  const response = await apiClient.get<InventoryValuationRow[]>('/reports/inventory-valuation/', {
    params: { ...branchParam(filters.branchId) },
  })
  return response.data
}

export async function getExpiredStock(filters: BranchOnlyReportFilters): Promise<ExpiredStockRow[]> {
  const response = await apiClient.get<ExpiredStockRow[]>('/reports/expired-stock/', {
    params: { ...branchParam(filters.branchId) },
  })
  return response.data
}

export interface NearExpiryReportFilters {
  branchId?: number | null
  days: number
}

export async function getNearExpiryStock(filters: NearExpiryReportFilters): Promise<NearExpiryStockRow[]> {
  const response = await apiClient.get<NearExpiryStockRow[]>('/reports/near-expiry-stock/', {
    params: { days: filters.days, ...branchParam(filters.branchId) },
  })
  return response.data
}

export async function getCashShiftClosures(filters: DateRangeReportFilters): Promise<CashShiftClosureRow[]> {
  const response = await apiClient.get<CashShiftClosureRow[]>('/reports/cash-shift-closures/', {
    params: { date_from: filters.dateFrom, date_to: filters.dateTo, ...branchParam(filters.branchId) },
  })
  return response.data
}

// Observación de sesión (ronda "3 piezas", punto 3): drill-down de un
// turno individual — no toma date_from/date_to/branch, solo el id del
// turno (ya viene de una fila de getCashShiftClosures).
export async function getCashShiftDetail(shiftId: number): Promise<CashShiftDetail> {
  const response = await apiClient.get<CashShiftDetail>('/reports/cash-shift-detail/', {
    params: { shift: shiftId },
  })
  return response.data
}

// Punto 11: exportación a Excel de "los 4 reportes existentes" (los que
// ya estaban en esta pantalla antes de esta sesión: ventas -por
// producto/categoría/cajero, un solo endpoint con group_by-, valuación de
// inventario, mermas por caducidad y cierres de caja). Próximos a
// caducar (punto 4 de esta misma sesión) no entra — no es de "los 4
// existentes" que pidió este punto.
export async function exportSalesByProduct(filters: DateRangeReportFilters): Promise<void> {
  await downloadExcel(
    '/reports/sales-by-product/',
    { date_from: filters.dateFrom, date_to: filters.dateTo, group_by: 'product', ...branchParam(filters.branchId) },
    'ventas-por-producto.xlsx',
  )
}

export async function exportSalesByCategory(filters: DateRangeReportFilters): Promise<void> {
  await downloadExcel(
    '/reports/sales-by-product/',
    { date_from: filters.dateFrom, date_to: filters.dateTo, group_by: 'category', ...branchParam(filters.branchId) },
    'ventas-por-categoria.xlsx',
  )
}

export async function exportSalesByCashier(filters: DateRangeReportFilters): Promise<void> {
  await downloadExcel(
    '/reports/sales-by-product/',
    { date_from: filters.dateFrom, date_to: filters.dateTo, group_by: 'cashier', ...branchParam(filters.branchId) },
    'ventas-por-cajero.xlsx',
  )
}

export async function exportInventoryValuation(filters: BranchOnlyReportFilters): Promise<void> {
  await downloadExcel(
    '/reports/inventory-valuation/', { ...branchParam(filters.branchId) }, 'valuacion-de-inventario.xlsx',
  )
}

export async function exportExpiredStock(filters: BranchOnlyReportFilters): Promise<void> {
  await downloadExcel('/reports/expired-stock/', { ...branchParam(filters.branchId) }, 'mermas-por-caducidad.xlsx')
}

export async function exportCashShiftClosures(filters: DateRangeReportFilters): Promise<void> {
  await downloadExcel(
    '/reports/cash-shift-closures/',
    { date_from: filters.dateFrom, date_to: filters.dateTo, ...branchParam(filters.branchId) },
    'cierres-de-caja.xlsx',
  )
}

export async function exportCashShiftDetail(shiftId: number): Promise<void> {
  await downloadExcel('/reports/cash-shift-detail/', { shift: shiftId }, 'cierre-de-turno-detallado.xlsx')
}
