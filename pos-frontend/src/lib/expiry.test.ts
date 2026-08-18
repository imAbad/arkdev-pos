import { describe, expect, it } from 'vitest'
import { isNearExpiry } from './expiry'

function isoDateInDays(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date.toISOString().slice(0, 10)
}

describe('isNearExpiry', () => {
  it('null (sin lotes) nunca es próximo a caducar', () => {
    expect(isNearExpiry(null)).toBe(false)
  })

  it('dentro de la ventana de 7 días es próximo a caducar', () => {
    expect(isNearExpiry(isoDateInDays(3))).toBe(true)
  })

  it('hoy mismo (0 días) cuenta como próximo a caducar', () => {
    expect(isNearExpiry(isoDateInDays(0))).toBe(true)
  })

  it('fuera de la ventana de 7 días NO es próximo a caducar', () => {
    expect(isNearExpiry(isoDateInDays(20))).toBe(false)
  })

  it('ya caducado no cuenta como "próximo" a caducar (es otro estado)', () => {
    expect(isNearExpiry(isoDateInDays(-1))).toBe(false)
  })
})
