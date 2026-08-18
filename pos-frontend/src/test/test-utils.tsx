// Helper para probar UNA pantalla aislada (OpenShiftScreen, SaleScreen)
// sin pasar por un login real cada vez — provee un AuthContext ya
// resuelto ("ya hizo login, ya tiene branch/company settings"). Las
// llamadas de API que la pantalla SÍ hace (buscar producto, abrir turno,
// cobrar) siguen yendo por la red real interceptada por MSW — esto solo
// evita repetir el bootstrap de autenticación en cada test.
//
// Para probar el LOGIN en sí (o la navegación entre pantallas que decide
// AuthProvider/App), no uses esto — renderiza <App/> real con MSW, como
// en App.test.tsx.
import { render, type RenderOptions } from '@testing-library/react'
import type { ReactElement } from 'react'
import { AuthContext, type AuthContextValue } from '@/features/auth/AuthProvider'
import type { NavigationContextValue } from '@/App'
import { makeBranch, makeCompanySettings, makeProfile } from '@/test/fixtures'

// Un solo lugar para el shape completo de NavigationContextValue — cada
// pantalla nueva de administración (módulos, catálogo, usuarios, config.
// de tienda) le agrega un par open*/close* a App.tsx, y sin este helper
// cada test que arma el value a mano se rompe cada vez que eso pasa.
export function fakeNavigationValue(overrides: Partial<NavigationContextValue> = {}): NavigationContextValue {
  return {
    view: 'main',
    openReports: () => {},
    closeReports: () => {},
    openModules: () => {},
    closeModules: () => {},
    openCatalog: () => {},
    closeCatalog: () => {},
    openLowStock: () => {},
    closeLowStock: () => {},
    openUsers: () => {},
    closeUsers: () => {},
    openBranding: () => {},
    closeBranding: () => {},
    ...overrides,
  }
}

export function fakeAuthValue(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    status: 'authenticated',
    profile: makeProfile(),
    branch: makeBranch(),
    companySettings: makeCompanySettings(),
    login: async () => true,
    loginError: null,
    loggingIn: false,
    logout: () => {},
    sessionExpiredNotice: null,
    refreshCompanySettings: async () => {},
    ...overrides,
  }
}

export function renderWithAuth(
  ui: ReactElement,
  authOverrides: Partial<AuthContextValue> = {},
  options?: Omit<RenderOptions, 'wrapper'>,
) {
  const value = fakeAuthValue(authOverrides)
  return render(<AuthContext.Provider value={value}>{ui}</AuthContext.Provider>, options)
}

export * from '@testing-library/react'
