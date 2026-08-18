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
