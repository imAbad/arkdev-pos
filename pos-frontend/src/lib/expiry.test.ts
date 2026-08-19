import { describe, expect, it } from 'vitest'
import { isNearExpiry } from './expiry'

/** Mismo cuidado que daysUntil() en expiry.ts: construir el string a mano
 * desde los componentes LOCALES evita el corrimiento de día de
 * toISOString() (UTC) — en una zona de offset negativo (ej. México,
 * UTC-6) y hora local avanzada, toISOString() ya cayó en el día
 * siguiente en UTC, lo que le pasaba a isNearExpiry() una fecha
 * equivocada y rompía el test de "-1 día" de forma intermitente según
 * la hora del día en que corriera. */
function isoDateInDays(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
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
