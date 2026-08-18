import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthProvider'
import { t } from '@/i18n'

/** Barra de marca — azul (accent_color del tenant), solo para identidad
 * y cerrar sesión (ver index.css: nunca para botones de acción). Punto
 * 13: la navegación entre pantallas se movió al Sidebar — antes vivía
 * acá como un botón por pantalla (ViewKey a mano), ya no cabía con 6+
 * destinos de administración. */
export function AppHeader() {
  const { companySettings, branch, logout } = useAuth()
  const businessName = companySettings?.business_name?.trim() || t.common.appName

  return (
    <header className="flex items-center justify-between gap-4 bg-accent px-6 py-4 text-white print:hidden">
      <div className="flex items-center gap-3">
        {companySettings?.logo && (
          <img src={companySettings.logo} alt="" className="h-10 w-10 rounded-full object-cover" />
        )}
        <div>
          <p className="text-xl font-bold leading-tight">{businessName}</p>
          {branch && <p className="text-sm text-white/80 leading-tight">{branch.name}</p>}
        </div>
      </div>
      <Button variant="neutral" size="compact" onClick={logout}>
        {t.common.logout}
      </Button>
    </header>
  )
}
