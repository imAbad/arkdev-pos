import { useEffect, useState, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/features/auth/AuthProvider'
import { LoginScreen } from '@/features/auth/LoginScreen'
import { OpenShiftScreen } from '@/features/shift/OpenShiftScreen'
import { SaleScreen } from '@/features/sales/SaleScreen'
import { ReportsScreen } from '@/features/reports/ReportsScreen'
import { ModuleSettingsScreen } from '@/features/admin/ModuleSettingsScreen'
import { UserManagementScreen } from '@/features/admin/UserManagementScreen'
import { StoreBrandingScreen } from '@/features/admin/StoreBrandingScreen'
import { RelatedProductsScreen } from '@/features/catalog/RelatedProductsScreen'
import { LowStockScreen } from '@/features/catalog/LowStockScreen'
import { AppLayout } from '@/components/app-layout'
import { isAdministrator, isAdministratorOrSupervisor } from '@/lib/permissions'
import { getCurrentShift } from '@/services/api/salesApi'
import { t } from '@/i18n'
import type { CashShift } from '@/types/api'

/** Punto 13: rutas reales (react-router-dom) con un sidebar que se
 * adapta al rol de quien inició sesión — reemplaza el NavigationContext/
 * ViewKey a mano que arquitectura_tecnica_pos.md §3 ya marcaba como
 * temporal ("se agrega un router cuando haya navegación real que lo
 * justifique -catálogo, reportes, admin- no antes"). Con 6 pantallas de
 * administración además de vender, ese momento ya llegó.
 *
 * El gate de rol aquí es UX (evita un 403 crudo si alguien escribe la
 * URL a mano), no el control de acceso real — ese sigue siendo el
 * backend (core.permissions.*), esto solo evita mostrar una pantalla que
 * de todas formas va a rechazar cada request. */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { profile } = useAuth()
  if (!isAdministrator(profile)) return <Navigate to="/" replace />
  return <>{children}</>
}

function RequireAdminOrSupervisor({ children }: { children: ReactNode }) {
  const { profile } = useAuth()
  if (!isAdministratorOrSupervisor(profile)) return <Navigate to="/" replace />
  return <>{children}</>
}

/** El flujo de venta (abrir turno -> vender) vive en "/" tal cual estaba
 * antes de este punto — el router solo reemplaza cómo se llega a las
 * OTRAS pantallas, no cómo se abre turno o se vende. */
function SaleFlowScreen() {
  const [shift, setShift] = useState<CashShift | null | 'loading'>('loading')

  useEffect(() => {
    getCurrentShift().then(setShift)
  }, [])

  if (shift === 'loading') {
    return <FullScreenMessage message={t.common.loading} />
  }

  if (shift === null) {
    return <OpenShiftScreen onShiftOpened={setShift} />
  }

  return <SaleScreen shift={shift} />
}

function AuthedApp() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<SaleFlowScreen />} />
          <Route path="/stock-bajo" element={<LowStockScreen />} />
          <Route
            path="/reportes"
            element={
              <RequireAdminOrSupervisor>
                <ReportsScreen />
              </RequireAdminOrSupervisor>
            }
          />
          <Route
            path="/modulos"
            element={
              <RequireAdmin>
                <ModuleSettingsScreen />
              </RequireAdmin>
            }
          />
          <Route
            path="/catalogo/relacionados"
            element={
              <RequireAdmin>
                <RelatedProductsScreen />
              </RequireAdmin>
            }
          />
          <Route
            path="/usuarios"
            element={
              <RequireAdmin>
                <UserManagementScreen />
              </RequireAdmin>
            }
          />
          <Route
            path="/mi-negocio"
            element={
              <RequireAdmin>
                <StoreBrandingScreen />
              </RequireAdmin>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

function FullScreenMessage({ message }: { message: string }) {
  return (
    <div className="flex min-h-svh items-center justify-center bg-surface-muted">
      <p className="text-xl text-ink/70">{message}</p>
    </div>
  )
}

function AppGate() {
  const { status } = useAuth()

  if (status === 'loading') {
    return <FullScreenMessage message={t.common.loading} />
  }

  if (status === 'unauthenticated') {
    return <LoginScreen />
  }

  return <AuthedApp />
}

export default function App() {
  return (
    <AuthProvider>
      <AppGate />
    </AuthProvider>
  )
}
