// Handlers de MSW por default (camino feliz) — cada test que necesite un
// caso distinto (error, lista vacía, etc.) los sobreescribe con
// `server.use(...)` sin tocar estos. Interceptan la llamada HTTP real que
// hace axios; los módulos de src/services/api/*.ts corren tal cual, sin
// mockear ninguna función de la app — solo se mockea el backend.
import { http, HttpResponse } from 'msw'
import {
  makeBranch,
  makeCashRegister,
  makeCompanySettings,
  makeProfile,
} from '@/test/fixtures'
import type { Paginated } from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

function paginated<T>(results: T[]): Paginated<T> {
  return { count: results.length, next: null, previous: null, results }
}

export const handlers = [
  http.post(`${BASE}/auth/token/`, () =>
    HttpResponse.json({ access: 'test-access-token', refresh: 'test-refresh-token' }),
  ),

  http.get(`${BASE}/user-profiles/me/`, () => HttpResponse.json(makeProfile())),

  http.get(`${BASE}/branches/:id`, () => HttpResponse.json(makeBranch())),

  http.get(`${BASE}/company-settings/`, () => HttpResponse.json(paginated([makeCompanySettings()]))),

  http.get(`${BASE}/cash-shifts/current/`, () =>
    HttpResponse.json({ detail: 'No tienes un turno abierto.' }, { status: 404 }),
  ),

  http.get(`${BASE}/cash-registers/`, () => HttpResponse.json(paginated([makeCashRegister()]))),

  // Punto 7: AppHeader se monta en casi toda pantalla y siempre pide esto
  // — default vacío para no obligar a cada test no relacionado con stock
  // bajo a mockearlo explícitamente (mismo criterio que el resto de esta
  // lista).
  http.get(`${BASE}/low-stock/`, () => HttpResponse.json([])),
]
