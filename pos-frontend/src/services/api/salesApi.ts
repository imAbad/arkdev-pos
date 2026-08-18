import axios from 'axios'
import { apiClient } from '@/lib/api-client'
import type { CashRegister, CashShift, Paginated, PaymentMethod, Sale } from '@/types/api'

export async function listCashRegisters(): Promise<CashRegister[]> {
  const response = await apiClient.get<Paginated<CashRegister>>('/cash-registers/')
  return response.data.results
}

/** null si el cajero no tiene un turno abierto ahora mismo (404 de la API,
 * no es un error — se resuelve así a propósito, no se relanza). */
export async function getCurrentShift(): Promise<CashShift | null> {
  try {
    const response = await apiClient.get<CashShift>('/cash-shifts/current/')
    return response.data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

/** null si esa caja no tiene un turno abierto — no es un error (404), se
 * resuelve así igual que getCurrentShift(). Devuelve el turno abierto sea
 * de quien sea (no filtra por usuario), a diferencia de getCurrentShift. */
export async function getShiftForRegister(cashRegisterId: number): Promise<CashShift | null> {
  try {
    const response = await apiClient.get<CashShift>('/cash-shifts/for-register/', {
      params: { cash_register_id: cashRegisterId },
    })
    return response.data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

export async function openShift(cashRegisterId: number, openingBalance: string): Promise<CashShift> {
  const response = await apiClient.post<CashShift>('/cash-shifts/open-shift/', {
    cash_register_id: cashRegisterId,
    opening_balance: openingBalance,
  })
  return response.data
}

/** Arqueo ciego a propósito: el backend solo calcula/revela expected_*
 * DESPUÉS de recibir lo que el cajero contó — nunca se le pide al backend
 * el expected_* por adelantado. */
export async function closeShift(
  shiftId: number,
  actualClosingBalance: string,
  actualVoucherTotal: string,
): Promise<CashShift> {
  const response = await apiClient.post<CashShift>(`/cash-shifts/${shiftId}/close-shift/`, {
    actual_closing_balance: actualClosingBalance,
    actual_voucher_total: actualVoucherTotal,
  })
  return response.data
}

export interface CreateSaleLineInput {
  product_id: number
  batch_id?: number
  quantity: string
  unit_price: string
}

export interface CreateSalePaymentInput {
  method: PaymentMethod
  amount: string
  reference?: string
}

export interface CreateSaleInput {
  cash_shift: number
  details: CreateSaleLineInput[]
  payments: CreateSalePaymentInput[]
}

export async function createSale(input: CreateSaleInput): Promise<Sale> {
  const response = await apiClient.post<Sale>('/sales/create-sale/', input)
  return response.data
}
