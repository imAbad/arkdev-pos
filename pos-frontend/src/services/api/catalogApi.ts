import { apiClient } from '@/lib/api-client'
import type { Paginated, Product } from '@/types/api'

export async function searchProducts(query: string): Promise<Product[]> {
  if (!query.trim()) return []
  const response = await apiClient.get<Paginated<Product>>('/products/', {
    params: { search: query },
  })
  return response.data.results
}
