import { createContext, useContext, useEffect, useState } from 'react'
import { AuthProvider, useAuth } from '@/features/auth/AuthProvider'
import { LoginScreen } from '@/features/auth/LoginScreen'
import { OpenShiftScreen } from '@/features/shift/OpenShiftScreen'
import { SaleScreen } from '@/features/sales/SaleScreen'
import { ReportsScreen } from '@/features/reports/ReportsScreen'
import { getCurrentShift } from '@/services/api/salesApi'
import { t } from '@/i18n'
import type { CashShift } from '@/types/api'

// Navegación mínima sin router (a propósito — ver arquitectura_tecnica_pos.md
// §3: "se agrega un router cuando haya navegación real que lo justifique
// -catálogo, reportes, admin- no antes"). Reportes es la primera pantalla
// que necesita ser alcanzable independientemente del flujo turno/venta
// (un administrador puede querer ver reportes sin abrir turno), así que
// vive en un estado de vista simple aquí, no dentro de SaleScreen.
export interface NavigationContextValue {
  view: 'main' | 'reports'
  openReports: () => void
  closeReports: () => void
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
})

export function useNavigation(): NavigationContextValue {
  return useContext(NavigationContext)
}

function AppScreens() {
  const { status } = useAuth()
  const [shift, setShift] = useState<CashShift | null | 'loading'>('loading')
  const [view, setView] = useState<'main' | 'reports'>('main')

  useEffect(() => {
    if (status !== 'authenticated') return
    setShift('loading')
    getCurrentShift().then(setShift)
  }, [status])

  const navigationValue: NavigationContextValue = {
    view,
    openReports: () => setView('reports'),
    closeReports: () => setView('main'),
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
