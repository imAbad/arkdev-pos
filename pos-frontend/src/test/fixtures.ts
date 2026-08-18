// Factories de datos de prueba con la forma EXACTA de los serializers
// reales (src/types/api.ts, leído del backend, no inventado) — cualquier
// test parte de estas y sobreescribe solo lo que le importa.
import type { Branch, CashRegister, CashShift, CompanySettings, Product, Sale, UserProfile } from '@/types/api'

export function makeProfile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    id: 1,
    email: 'cajero@donchuy.test',
    branch: 1,
    role: 'CAJERO',
    capabilities: { handles_cash: true },
    company: 1,
    ...overrides,
  }
}

export function makeBranch(overrides: Partial<Branch> = {}): Branch {
  return {
    id: 1,
    name: 'Centro',
    address: 'Av. Siempre Viva 123',
    company: 1,
    ...overrides,
  }
}

export function makeCompanySettings(overrides: Partial<CompanySettings> = {}): CompanySettings {
  return {
    id: 1,
    company: 1,
    enabled_modules: {},
    business_name: 'Don Chuy Abarrotes',
    logo: null,
    accent_color: '#1E5B94',
    ...overrides,
  }
}

export function makeCashRegister(overrides: Partial<CashRegister> = {}): CashRegister {
  return {
    id: 1,
    branch: 1,
    name: 'Caja 1',
    is_active: true,
    company: 1,
    ...overrides,
  }
}

export function makeShift(overrides: Partial<CashShift> = {}): CashShift {
  return {
    id: 1,
    cash_register: 1,
    user: 1,
    user_email: 'cajero@donchuy.test',
    closed_by: null,
    closed_by_email: null,
    opened_at: '2026-08-18T12:00:00Z',
    closed_at: null,
    opening_balance: '500.00',
    expected_closing_balance: null,
    actual_closing_balance: null,
    cash_difference: null,
    expected_voucher_total: null,
    actual_voucher_total: null,
    voucher_difference: null,
    status: 'OPEN',
    company: 1,
    ...overrides,
  }
}

export function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    id: 1,
    name: 'Refresco de cola 600ml',
    sku: 'REF-600',
    barcode: null,
    category: 1,
    supplier: null,
    unit_type: 'PIEZA',
    requires_batch: false,
    variant_attributes: null,
    cost_price: '12.00',
    sale_price: '18.00',
    tax_rate: '16.00',
    min_stock: 0,
    image: null,
    company: 1,
    ...overrides,
  }
}

export function makeSale(overrides: Partial<Sale> = {}): Sale {
  return {
    id: 1,
    branch: 1,
    cash_register: 1,
    cash_shift: 1,
    client: null,
    client_name: null,
    client_uuid: '11111111-1111-1111-1111-111111111111',
    occurred_at: '2026-08-18T12:05:00Z',
    subtotal: '18.00',
    discount_amount: '0.00',
    tax_amount: '2.88',
    total: '20.88',
    status: 'COMPLETED',
    details: [],
    payments: [],
    company: 1,
    created_at: '2026-08-18T12:05:00Z',
    ...overrides,
  }
}
