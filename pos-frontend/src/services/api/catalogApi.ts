import { apiClient } from '@/lib/api-client'
import type { Paginated, Product } from '@/types/api'

export async function searchProducts(query: string): Promise<Product[]> {
  if (!query.trim()) return []
  const response = await apiClient.get<Paginated<Product>>('/products/', {
    params: { search: query },
  })
  return response.data.results
}

export async function getProduct(id: number): Promise<Product> {
  const response = await apiClient.get<Product>(`/products/${id}/`)
  return response.data
}

export async function updateProductRelatedProducts(id: number, relatedProductIds: number[]): Promise<Product> {
  const response = await apiClient.patch<Product>(`/products/${id}/`, { related_products: relatedProductIds })
  return response.data
}
