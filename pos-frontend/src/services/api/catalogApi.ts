import { apiClient } from '@/lib/api-client'
import type { Batch, Category, LowStockRow, Paginated, Product, Supplier } from '@/types/api'

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

export async function getLowStockProducts(): Promise<LowStockRow[]> {
  const response = await apiClient.get<LowStockRow[]>('/low-stock/')
  return response.data
}

// Observación de sesión, punto 2: pantalla de Inventario — el backend
// (categorías/proveedores/productos/lotes) ya existía completo desde el
// punto 8, solo faltaba que el frontend lo consumiera.
export async function listAllProducts(branchId?: number): Promise<Product[]> {
  const response = await apiClient.get<Paginated<Product>>('/products/', {
    params: { page_size: 500, ...(branchId ? { branch: branchId } : {}) },
  })
  return response.data.results
}

export interface ProductInput {
  name: string
  sku: string
  barcode?: string | null
  category: number
  supplier?: number | null
  unit_type: Product['unit_type']
  requires_batch: boolean
  cost_price: string
  sale_price: string
  tax_rate: string
  min_stock: number
}

export async function createProduct(input: ProductInput): Promise<Product> {
  const response = await apiClient.post<Product>('/products/', input)
  return response.data
}

export async function updateProduct(id: number, input: Partial<ProductInput>): Promise<Product> {
  const response = await apiClient.patch<Product>(`/products/${id}/`, input)
  return response.data
}

export async function listCategories(): Promise<Category[]> {
  const response = await apiClient.get<Paginated<Category>>('/categories/', { params: { page_size: 500 } })
  return response.data.results
}

export async function listSuppliers(): Promise<Supplier[]> {
  const response = await apiClient.get<Paginated<Supplier>>('/suppliers/', { params: { page_size: 500 } })
  return response.data.results
}

export async function listBatchesForProduct(productId: number): Promise<Batch[]> {
  const response = await apiClient.get<Paginated<Batch>>('/batches/', { params: { product: productId, page_size: 500 } })
  return response.data.results
}

export interface BatchInput {
  product: number
  branch: number
  batch_number: string
  initial_quantity: number
  expiration_date: string
}

export async function createBatch(input: BatchInput): Promise<Batch> {
  const response = await apiClient.post<Batch>('/batches/', input)
  return response.data
}
