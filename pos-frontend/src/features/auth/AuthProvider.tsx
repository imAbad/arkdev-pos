import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import axios from 'axios'
import { login as loginRequest } from '@/services/api/authApi'
import { getBranch, getMyCompanySettings, getMyProfile } from '@/services/api/tenantsApi'
import { clearAccessToken, getAccessToken, setAccessToken } from '@/lib/auth-storage'
import { onSessionExpired } from '@/lib/api-client'
import { applyAccentColor } from '@/lib/theme'
import { t } from '@/i18n'
import type { Branch, CompanySettings, UserProfile } from '@/types/api'

// /auth/token/ es la vista de SimpleJWT sin envolver — su mensaje de error
// ("No active account found...") viene en inglés y no pasa por
// core.exceptions.api_exception_handler. Nunca se muestra tal cual (ver
// principio de diseño: nada de inglés/jerga visible) — se traduce aquí
// según el código HTTP, no se usa apiErrorMessage() para este caso.
// Exportada (no solo interna) para poder fijar el mapeo con un test
// directo — ver AuthProvider.test.tsx.
export function loginErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    return t.login.errorInvalid
  }
  return t.login.errorGeneric
}

export type AuthStatus = 'loading' | 'unauthenticated' | 'authenticated'

export interface AuthContextValue {
  status: AuthStatus
  profile: UserProfile | null
  branch: Branch | null
  companySettings: CompanySettings | null
  login: (email: string, password: string) => Promise<boolean>
  loginError: string | null
  loggingIn: boolean
  logout: () => void
  sessionExpiredNotice: string | null
}

// Exportado para que los tests de pantallas individuales (OpenShiftScreen,
// SaleScreen) puedan renderizar con <AuthContext.Provider value={...}>
// directo, sin pasar por un login real vía MSW cada vez — ver
// src/test/test-utils.tsx::renderWithAuth. AuthProvider sigue siendo la
// única forma real de producir ese value en la app.
export const AuthContext = createContext<AuthContextValue | null>(null)

// Login por email confirma el tenant (no hay subdominio propio por
// cliente — decisiones_post_auditoria.md §5) — por eso la pantalla de
// login NO puede mostrar marca de un tenant específico todavía; el
// accent_color/logo se aplican recién después de este bloque, cuando ya
// se sabe a qué tenant pertenece quien inició sesión.
async function loadTenantContext(): Promise<{ profile: UserProfile; branch: Branch; companySettings: CompanySettings | null }> {
  const profile = await getMyProfile()
  const [branch, companySettings] = await Promise.all([
    getBranch(profile.branch),
    getMyCompanySettings(),
  ])
  return { profile, branch, companySettings }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [branch, setBranch] = useState<Branch | null>(null)
  const [companySettings, setCompanySettings] = useState<CompanySettings | null>(null)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loggingIn, setLoggingIn] = useState(false)
  const [sessionExpiredNotice, setSessionExpiredNotice] = useState<string | null>(null)

  useEffect(() => {
    applyAccentColor(companySettings?.accent_color)
  }, [companySettings])

  // Token rechazado a medio uso (no login) — vaciar todo y mandar al login
  // con un aviso explícito, nunca una pantalla en blanco o un "Cargando…"
  // infinito. El carrito de una venta en curso NO se preserva (ver el
  // texto del aviso) — SaleScreen se desmonta al cambiar `status`.
  useEffect(() => {
    return onSessionExpired(() => {
      setProfile(null)
      setBranch(null)
      setCompanySettings(null)
      setStatus('unauthenticated')
      setSessionExpiredNotice(t.common.sessionExpiredNotice)
    })
  }, [])

  useEffect(() => {
    if (!getAccessToken()) {
      setStatus('unauthenticated')
      return
    }
    loadTenantContext()
      .then((context) => {
        setProfile(context.profile)
        setBranch(context.branch)
        setCompanySettings(context.companySettings)
        setStatus('authenticated')
      })
      .catch(() => {
        clearAccessToken()
        setStatus('unauthenticated')
      })
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setLoggingIn(true)
    setLoginError(null)
    setSessionExpiredNotice(null)
    try {
      const tokens = await loginRequest(email, password)
      setAccessToken(tokens.access)
      const context = await loadTenantContext()
      setProfile(context.profile)
      setBranch(context.branch)
      setCompanySettings(context.companySettings)
      setStatus('authenticated')
      return true
    } catch (error) {
      clearAccessToken()
      setLoginError(loginErrorMessage(error))
      return false
    } finally {
      setLoggingIn(false)
    }
  }, [])

  const logout = useCallback(() => {
    clearAccessToken()
    setProfile(null)
    setBranch(null)
    setCompanySettings(null)
    setSessionExpiredNotice(null)
    setStatus('unauthenticated')
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      status, profile, branch, companySettings, login, loginError, loggingIn, logout, sessionExpiredNotice,
    }),
    [status, profile, branch, companySettings, login, loginError, loggingIn, logout, sessionExpiredNotice],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth debe usarse dentro de <AuthProvider>.')
  return context
}
