// Formas exactas leídas de los serializers reales del backend (no de la
// documentación) — pos-backend/tenants|sales|catalog/serializers.py.

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface TokenPair {
  access: string
  refresh: string
}

export type Role = 'CAJERO' | 'ADMINISTRADOR'

export interface UserProfile {
  id: number
  email: string
  branch: number
  role: Role
  capabilities: {
    handles_cash?: boolean
    can_authorize_exceptions?: boolean
  }
  company: number
}

export interface Branch {
  id: number
  name: string
  address: string
  company: number
}

export interface CompanySettings {
  id: number
  company: number
  enabled_modules: Record<string, boolean>
  business_name: string
  logo: string | null
  accent_color: string
}

export interface CashRegister {
  id: number
  branch: number
  name: string
  is_active: boolean
  company: number
}

export type ShiftStatus = 'OPEN' | 'CLOSED'

export interface CashShift {
  id: number
  cash_register: number
  user: number
  user_email: string
  closed_by: number | null
  closed_by_email: string | null
  opened_at: string
  closed_at: string | null
  opening_balance: string
  expected_closing_balance: string | null
  actual_closing_balance: string | null
  cash_difference: string | null
  expected_voucher_total: string | null
  actual_voucher_total: string | null
  voucher_difference: string | null
  status: ShiftStatus
  company: number
}

export type UnitType = 'PIEZA' | 'KG' | 'GRAMO' | 'LITRO' | 'PAQUETE' | 'SERVICIO'

export interface RelatedProductSummary {
  id: number
  name: string
  sale_price: string
}

export interface Product {
  id: number
  name: string
  sku: string
  barcode: string | null
  category: number
  supplier: number | null
  unit_type: UnitType
  requires_batch: boolean
  variant_attributes: Record<string, unknown> | null
  cost_price: string
  sale_price: string
  tax_rate: string
  min_stock: number
  image: string | null
  nearest_batch_expiration: string | null
  related_products: number[]
  related_products_detail: RelatedProductSummary[]
  company: number
}

export type PaymentMethod = 'CASH' | 'CARD' | 'TRANSFER' | 'CREDIT'

export interface SaleDetail {
  id: number
  product: number
  product_name: string
  product_unit_type: UnitType
  batch: number | null
  quantity: string
  unit_price: string
  tax_rate_applied: string
  tax_amount: string
  subtotal: string
}

export interface Payment {
  id: number
  method: PaymentMethod
  amount: string
  reference: string
}

export type SaleStatus = 'COMPLETED' | 'CANCELLED' | 'REFUNDED'

export interface Sale {
  id: number
  branch: number
  cash_register: number
  cash_shift: number
  client: number | null
  client_name: string | null
  client_uuid: string
  occurred_at: string
  subtotal: string
  discount_amount: string
  tax_amount: string
  total: string
  status: SaleStatus
  details: SaleDetail[]
  payments: Payment[]
  company: number
  created_at: string
}

export interface ApiErrorBody {
  code?: string
  detail?: unknown
}

export interface SalesByProductRow {
  product_id: number
  product_name: string
  category_name: string
  quantity_sold: string
  revenue: string
  tax: string
}

export interface SalesByCategoryRow {
  category_id: number | null
  category_name: string
  quantity_sold: string
  revenue: string
  tax: string
}

export interface SalesByCashierRow {
  cashier_id: number
  cashier_email: string
  quantity_sold: string
  revenue: string
  tax: string
}

export interface InventoryValuationRow {
  product_id: number
  product_name: string
  category_name: string
  quantity: number
  valuation: string
}

export interface NearExpiryStockRow {
  batch_id: number
  batch_number: string
  product_id: number
  product_name: string
  branch_id: number
  branch_name: string
  expiration_date: string
  days_to_expire: number
  quantity: number
  valuation: string
}

export interface ExpiredStockRow {
  batch_id: number
  batch_number: string
  product_id: number
  product_name: string
  branch_id: number
  branch_name: string
  expiration_date: string
  quantity: number
  valuation: string
}

export interface CashShiftClosureRow {
  id: number
  branch_name: string
  register_name: string
  user_email: string
  opened_at: string
  closed_at: string
  opening_balance: string
  expected_closing_balance: string
  actual_closing_balance: string
  cash_difference: string
  expected_voucher_total: string
  actual_voucher_total: string
  voucher_difference: string
}
