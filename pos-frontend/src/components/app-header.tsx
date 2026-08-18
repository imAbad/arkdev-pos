import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthProvider'
import { useNavigation } from '@/App'
import { isAdministrator, isAdministratorOrSupervisor } from '@/lib/permissions'
import { getLowStockProducts } from '@/services/api/catalogApi'
import { t } from '@/i18n'

/** Barra de marca — azul (accent_color del tenant), solo para
 * identidad/navegación, nunca para botones de acción (ver index.css). */
export function AppHeader() {
  const { companySettings, branch, profile, logout } = useAuth()
  const { view, openReports, openModules, openCatalog, openLowStock, openUsers, openBranding } = useNavigation()
  const businessName = companySettings?.business_name?.trim() || t.common.appName
  const showReportsLink = view === 'main' && isAdministratorOrSupervisor(profile)
  const showModulesLink = view === 'main' && isAdministrator(profile)
  const showCatalogLink = view === 'main' && isAdministrator(profile)
  const showUsersLink = view === 'main' && isAdministrator(profile)
  const showBrandingLink = view === 'main' && isAdministrator(profile)

  // Punto 7: cualquier usuario que abre turno debe ver esto, no solo
  // admin/supervisor — mismo gate que el endpoint (HandlesCash). AppHeader
  // se monta en cada pantalla (no vive en el árbol una sola vez), así que
  // esto se recalcula al navegar — aceptable, es una query barata y ya es
  // el mismo patrón que el resto del header (sin caché propia todavía).
  const [lowStockCount, setLowStockCount] = useState(0)
  useEffect(() => {
    if (profile === null) return
    getLowStockProducts()
      .then((rows) => setLowStockCount(rows.length))
      .catch(() => {})
  }, [profile])

  return (
    <header className="flex items-center justify-between gap-4 bg-accent px-6 py-4 text-white">
      <div className="flex items-center gap-3">
        {companySettings?.logo && (
          <img src={companySettings.logo} alt="" className="h-10 w-10 rounded-full object-cover" />
        )}
        <div>
          <p className="text-xl font-bold leading-tight">{businessName}</p>
          {branch && <p className="text-sm text-white/80 leading-tight">{branch.name}</p>}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {showReportsLink && (
          <Button variant="neutral" size="compact" onClick={openReports}>
            {t.reports.navLink}
          </Button>
        )}
        {showModulesLink && (
          <Button variant="neutral" size="compact" onClick={openModules}>
            {t.modules.navLink}
          </Button>
        )}
        {showCatalogLink && (
          <Button variant="neutral" size="compact" onClick={openCatalog}>
            {t.relatedProducts.navLink}
          </Button>
        )}
        {showUsersLink && (
          <Button variant="neutral" size="compact" onClick={openUsers}>
            {t.users.navLink}
          </Button>
        )}
        {showBrandingLink && (
          <Button variant="neutral" size="compact" onClick={openBranding}>
            {t.branding.navLink}
          </Button>
        )}
        {lowStockCount > 0 && view !== 'low-stock' && (
          <button
            type="button"
            onClick={openLowStock}
            className="rounded-full border border-warning bg-warning-bg px-3 py-1 text-sm font-semibold text-warning"
          >
            {t.lowStock.badgeLabel} ({lowStockCount})
          </button>
        )}
        <Button variant="neutral" size="compact" onClick={logout}>
          {t.common.logout}
        </Button>
      </div>
    </header>
  )
}
