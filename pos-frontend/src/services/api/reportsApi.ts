import { apiClient } from '@/lib/api-client'
import type {
  CashShiftClosureRow,
  ExpiredStockRow,
  InventoryValuationRow,
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

export async function getCashShiftClosures(filters: DateRangeReportFilters): Promise<CashShiftClosureRow[]> {
  const response = await apiClient.get<CashShiftClosureRow[]>('/reports/cash-shift-closures/', {
    params: { date_from: filters.dateFrom, date_to: filters.dateTo, ...branchParam(filters.branchId) },
  })
  return response.data
}
