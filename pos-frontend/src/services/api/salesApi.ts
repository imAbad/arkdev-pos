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

export async function sendTicketByEmail(saleId: number, email: string, changeGiven?: number): Promise<void> {
  await apiClient.post(`/sales/${saleId}/send-ticket-email/`, {
    email,
    change_given: changeGiven && changeGiven > 0 ? changeGiven.toFixed(2) : undefined,
  })
}

/** Punto 10: revierte stock y cualquier cargo a crédito server-side —
 * este endpoint solo consume un token ya emitido por
 * requestSupervisorAuthorization (authApi.ts), no valida credenciales
 * directo. */
export async function cancelSale(saleId: number, supervisorAuthorizationToken: string): Promise<Sale> {
  const response = await apiClient.post<Sale>(`/sales/${saleId}/cancel/`, {
    supervisor_authorization_token: supervisorAuthorizationToken,
  })
  return response.data
}

/** Observación de sesión, punto 2: historial de ventas — mismo endpoint
 * de solo lectura que ya existía (GET /sales/), ahora con filtro de
 * fecha y orden más reciente primero del lado del backend. Devuelve
 * solo la primera página (25, PAGE_SIZE default) — suficiente para el
 * rango de fechas típico de este filtro; paginar más allá de eso queda
 * para cuando alguien lo necesite de verdad. */
export async function listSales(dateFrom?: string, dateTo?: string): Promise<Sale[]> {
  const response = await apiClient.get<Paginated<Sale>>('/sales/', {
    params: { date_from: dateFrom, date_to: dateTo },
  })
  return response.data.results
}
