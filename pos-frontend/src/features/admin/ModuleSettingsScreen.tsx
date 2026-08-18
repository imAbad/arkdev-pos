import { useState } from 'react'
import { AppHeader } from '@/components/app-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { apiErrorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { useNavigation } from '@/App'
import { useAuth } from '@/features/auth/AuthProvider'
import { updateCompanySettings } from '@/services/api/tenantsApi'
import { t } from '@/i18n'

// Únicas dos claves reales hoy — arquitectura_tecnica_pos.md §... define
// `enabled_modules` como `{'cfdi': false, 'multiple_branches': false, ...}`.
// No se inventan módulos nuevos que no correspondan a nada real todavía.
const MODULE_KEYS = ['cfdi', 'multiple_branches'] as const
type ModuleKey = (typeof MODULE_KEYS)[number]

const MODULE_LABELS: Record<ModuleKey, { name: string; description: string }> = {
  cfdi: { name: t.modules.cfdiName, description: t.modules.cfdiDescription },
  multiple_branches: { name: t.modules.multipleBranchesName, description: t.modules.multipleBranchesDescription },
}

export function ModuleSettingsScreen() {
  const { closeModules } = useNavigation()
  const { companySettings, refreshCompanySettings } = useAuth()
  const [savingKey, setSavingKey] = useState<ModuleKey | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [savedNotice, setSavedNotice] = useState(false)

  async function toggle(key: ModuleKey) {
    if (companySettings === null) return
    setSavingKey(key)
    setError(null)
    setSavedNotice(false)
    const current = Boolean(companySettings.enabled_modules[key])
    try {
      await updateCompanySettings(companySettings.id, {
        enabled_modules: { ...companySettings.enabled_modules, [key]: !current },
      })
      await refreshCompanySettings()
      setSavedNotice(true)
    } catch (err) {
      setError(apiErrorMessage(err, t.modules.errorGeneric))
    } finally {
      setSavingKey(null)
    }
  }

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      <AppHeader />

      <div className="flex flex-1 flex-col gap-6 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-ink">{t.modules.title}</h1>
            <p className="mt-2 text-lg text-ink/70">{t.modules.subtitle}</p>
          </div>
          <Button type="button" variant="neutral" onClick={closeModules}>
            {t.modules.back}
          </Button>
        </div>

        {companySettings === null ? (
          <p className="text-lg text-ink/70">{t.modules.loading}</p>
        ) : (
          <div className="flex flex-col gap-4">
            {MODULE_KEYS.map((key) => {
              const enabled = Boolean(companySettings.enabled_modules[key])
              const label = MODULE_LABELS[key]
              return (
                <Card key={key} className="flex items-center justify-between gap-6">
                  <div>
                    <p className="text-xl font-semibold text-ink">{label.name}</p>
                    <p className="mt-1 text-lg text-ink/70">{label.description}</p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={enabled}
                    aria-label={label.name}
                    disabled={savingKey === key}
                    onClick={() => toggle(key)}
                    className={cn(
                      'h-10 w-20 shrink-0 rounded-full border-2 transition-colors disabled:opacity-40',
                      enabled ? 'border-confirm bg-confirm' : 'border-border bg-white',
                    )}
                  >
                    <span
                      className={cn(
                        'block h-8 w-8 rounded-full bg-white shadow transition-transform',
                        enabled ? 'translate-x-10 bg-white' : 'translate-x-0 bg-border',
                      )}
                    />
                  </button>
                </Card>
              )
            })}
          </div>
        )}

        {savedNotice && <p className="text-lg font-medium text-confirm">{t.modules.saved}</p>}
        {error && (
          <p role="alert" className="text-lg font-medium text-cancel">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}
