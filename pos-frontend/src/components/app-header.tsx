import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthProvider'
import { useNavigation } from '@/App'
import { isAdministrator, isAdministratorOrSupervisor } from '@/lib/permissions'
import { t } from '@/i18n'

/** Barra de marca — azul (accent_color del tenant), solo para
 * identidad/navegación, nunca para botones de acción (ver index.css). */
export function AppHeader() {
  const { companySettings, branch, profile, logout } = useAuth()
  const { view, openReports, openModules, openCatalog } = useNavigation()
  const businessName = companySettings?.business_name?.trim() || t.common.appName
  const showReportsLink = view === 'main' && isAdministratorOrSupervisor(profile)
  const showModulesLink = view === 'main' && isAdministrator(profile)
  const showCatalogLink = view === 'main' && isAdministrator(profile)

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
        <Button variant="neutral" size="compact" onClick={logout}>
          {t.common.logout}
        </Button>
      </div>
    </header>
  )
}
