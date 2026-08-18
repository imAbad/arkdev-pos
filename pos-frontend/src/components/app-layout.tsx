import { Outlet } from 'react-router-dom'
import { AppHeader } from '@/components/app-header'
import { Sidebar } from '@/components/sidebar'

/** Punto 13: envoltorio único de sidebar + encabezado para toda la app
 * autenticada — antes cada pantalla se renderizaba a sí misma con su
 * propio <AppHeader/> (9 copias del mismo patrón). `min-h-svh` vive
 * aquí, no en cada pantalla. */
export function AppLayout() {
  return (
    <div className="flex min-h-svh bg-surface-muted">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <AppHeader />
        <main className="flex flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
