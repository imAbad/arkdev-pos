import { createContext, useContext, useEffect, useState } from 'react'
import { AuthProvider, useAuth } from '@/features/auth/AuthProvider'
import { LoginScreen } from '@/features/auth/LoginScreen'
import { OpenShiftScreen } from '@/features/shift/OpenShiftScreen'
import { SaleScreen } from '@/features/sales/SaleScreen'
import { ReportsScreen } from '@/features/reports/ReportsScreen'
import { ModuleSettingsScreen } from '@/features/admin/ModuleSettingsScreen'
import { RelatedProductsScreen } from '@/features/catalog/RelatedProductsScreen'
import { LowStockScreen } from '@/features/catalog/LowStockScreen'
import { getCurrentShift } from '@/services/api/salesApi'
import { t } from '@/i18n'
import type { CashShift } from '@/types/api'

// Navegación mínima sin router (a propósito — ver arquitectura_tecnica_pos.md
// §3: "se agrega un router cuando haya navegación real que lo justifique
// -catálogo, reportes, admin- no antes"). Reportes fue la primera pantalla
// alcanzable independientemente del flujo turno/venta; el resto de
// pantallas de administración (módulos, catálogo, usuarios, config. de
// tienda — puntos 3/8/9/12) siguen el mismo patrón por ahora. El punto 13
// de esta sesión reemplaza esto por un router real con sidebar — no antes,
// para no reescribir esto cinco veces mientras las pantallas se construyen.
export type ViewKey = 'main' | 'reports' | 'modules' | 'catalog' | 'low-stock'

export interface NavigationContextValue {
  view: ViewKey
  openReports: () => void
  closeReports: () => void
  openModules: () => void
  closeModules: () => void
  openCatalog: () => void
  closeCatalog: () => void
  openLowStock: () => void
  closeLowStock: () => void
}

// Sin valor por default null-y-throw (a diferencia de useAuth): AppHeader
// llama a este hook y se renderiza en tests de pantallas aisladas
// (renderWithAuth) que no envuelven con <App/> — un default silencioso
// (sin navegar a ningún lado) es más simple que forzar a cada test de
// pantalla a montar también este contexto. Exportado (no solo el hook)
// para que los tests de ReportsScreen puedan proveer un value propio con
// closeReports espiado — mismo patrón que AuthContext/renderWithAuth.
export const NavigationContext = createContext<NavigationContextValue>({
  view: 'main',
  openReports: () => {},
  closeReports: () => {},
  openModules: () => {},
  closeModules: () => {},
  openCatalog: () => {},
  closeCatalog: () => {},
  openLowStock: () => {},
  closeLowStock: () => {},
})

export function useNavigation(): NavigationContextValue {
  return useContext(NavigationContext)
}

function AppScreens() {
  const { status } = useAuth()
  const [shift, setShift] = useState<CashShift | null | 'loading'>('loading')
  const [view, setView] = useState<ViewKey>('main')

  useEffect(() => {
    if (status !== 'authenticated') return
    setShift('loading')
    getCurrentShift().then(setShift)
  }, [status])

  const navigationValue: NavigationContextValue = {
    view,
    openReports: () => setView('reports'),
    closeReports: () => setView('main'),
    openModules: () => setView('modules'),
    closeModules: () => setView('main'),
    openCatalog: () => setView('catalog'),
    closeCatalog: () => setView('main'),
    openLowStock: () => setView('low-stock'),
    closeLowStock: () => setView('main'),
  }

  return <NavigationContext.Provider value={navigationValue}>{renderScreen()}</NavigationContext.Provider>

  function renderScreen() {
    if (status === 'loading') {
      return <FullScreenMessage message={t.common.loading} />
    }

    if (status === 'unauthenticated') {
      return <LoginScreen />
    }

    if (view === 'reports') {
      return <ReportsScreen />
    }

    if (view === 'modules') {
      return <ModuleSettingsScreen />
    }

    if (view === 'catalog') {
      return <RelatedProductsScreen />
    }

    if (view === 'low-stock') {
      return <LowStockScreen />
    }

    if (shift === 'loading') {
      return <FullScreenMessage message={t.common.loading} />
    }

    if (shift === null) {
      return <OpenShiftScreen onShiftOpened={setShift} />
    }

    return <SaleScreen shift={shift} />
  }
}

function FullScreenMessage({ message }: { message: string }) {
  return (
    <div className="flex min-h-svh items-center justify-center bg-surface-muted">
      <p className="text-xl text-ink/70">{message}</p>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppScreens />
    </AuthProvider>
  )
}
