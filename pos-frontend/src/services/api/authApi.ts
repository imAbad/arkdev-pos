import { apiClient } from '@/lib/api-client'
import type { TokenPair } from '@/types/api'

export async function login(email: string, password: string): Promise<TokenPair> {
  const response = await apiClient.post<TokenPair>('/auth/token/', { email, password })
  return response.data
}
