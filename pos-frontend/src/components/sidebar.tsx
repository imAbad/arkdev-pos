import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '@/features/auth/AuthProvider'
import { isAdministrator, isAdministratorOrSupervisor } from '@/lib/permissions'
import { getLowStockProducts } from '@/services/api/catalogApi'
import { cn } from '@/lib/utils'
import { t } from '@/i18n'

/** Punto 13: reemplaza los botones de navegación que antes vivían en
 * AppHeader (uno por pantalla, ViewKey a mano) — con 6+ destinos de
 * administración ya no cabían como botones sueltos en el encabezado
 * (arquitectura_tecnica_pos.md §3 ya anticipaba este momento). Rutas
 * reales de react-router-dom en vez de NavigationContext/ViewKey. */
export function Sidebar() {
  const { profile } = useAuth()

  // Punto 7: mismo criterio que antes (visible a cualquier usuario, no
  // solo admin/supervisor) — ahora vive como parte del link en vez de un
  // badge flotante aparte en el header.
  const [lowStockCount, setLowStockCount] = useState(0)
  useEffect(() => {
    if (profile === null) return
    getLowStockProducts()
      .then((rows) => setLowStockCount(rows.length))
      .catch(() => {})
  }, [profile])

  return (
    <nav className="flex w-64 shrink-0 flex-col gap-1 border-r-2 border-border bg-white p-4 print:hidden">
      <SidebarLink to="/">{t.sidebar.sell}</SidebarLink>

      {lowStockCount > 0 && (
        <SidebarLink to="/stock-bajo" tone="warning">
          {t.lowStock.badgeLabel} ({lowStockCount})
        </SidebarLink>
      )}

      {isAdministratorOrSupervisor(profile) && <SidebarLink to="/reportes">{t.reports.navLink}</SidebarLink>}

      {isAdministrator(profile) && (
        <>
          <SidebarLink to="/modulos">{t.modules.navLink}</SidebarLink>
          <SidebarLink to="/catalogo/relacionados">{t.relatedProducts.navLink}</SidebarLink>
          <SidebarLink to="/usuarios">{t.users.navLink}</SidebarLink>
          <SidebarLink to="/mi-negocio">{t.branding.navLink}</SidebarLink>
        </>
      )}
    </nav>
  )
}

function SidebarLink({
  to,
  tone = 'default',
  children,
}: {
  to: string
  tone?: 'default' | 'warning'
  children: React.ReactNode
}) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        cn(
          'rounded-2xl px-4 py-3 text-lg font-semibold transition-colors',
          isActive
            ? 'bg-accent text-white'
            : tone === 'warning'
              ? 'text-warning hover:bg-warning-bg'
              : 'text-ink hover:bg-surface-muted',
        )
      }
    >
      {children}
    </NavLink>
  )
}
