import { apiClient } from '@/lib/api-client'
import type { Client, Paginated } from '@/types/api'

// Observación de sesión (ronda de 4 piezas, punto 3): venta a crédito en
// la pantalla de venta — el backend (Client/CreditAccount/charge_credit)
// ya existía completo, solo faltaba que el frontend lo consumiera.
export async function searchClients(query: string): Promise<Client[]> {
  if (!query.trim()) return []
  const response = await apiClient.get<Paginated<Client>>('/clients/', { params: { search: query } })
  return response.data.results
}

export interface CreateClientInput {
  name: string
  phone: string
}

// Alta rápida a mitad de venta: solo nombre y teléfono, los campos
// mínimos del modelo — sin credit_limit (se queda en 0 por default; un
// cliente nuevo así no puede fiar hasta que un administrador le asigne
// límite en algún lugar aparte, eso es consistente con el modelo actual,
// no un bug de este alta rápida).
export async function createClient(input: CreateClientInput): Promise<Client> {
  const response = await apiClient.post<Client>('/clients/', input)
  return response.data
}
