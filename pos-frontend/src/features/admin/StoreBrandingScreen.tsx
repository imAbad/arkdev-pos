import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { useAuth } from '@/features/auth/AuthProvider'
import { updateCompanyLogo, updateCompanySettings } from '@/services/api/tenantsApi'
import { t } from '@/i18n'

const HEX_COLOR_PATTERN = /^#[0-9A-Fa-f]{6}$/

/** Punto 12: pantalla de marca del negocio (nombre/logo/color),
 * ADMINISTRADOR-only — el color por default de un tenant nuevo ya es
 * azul `#1E5B94` (tenants.models.CompanySettings.accent_color), esta
 * pantalla es la única forma de cambiarlo desde acá en adelante; el
 * naranja/azul-morado que se ve en los tenants demo es solo cómo
 * seed_demo_data los distingue entre sí, no el default real (ver
 * comentario en ese archivo). */
export function StoreBrandingScreen() {
  const { companySettings, refreshCompanySettings } = useAuth()
  const [businessName, setBusinessName] = useState(companySettings?.business_name ?? '')
  const [accentColor, setAccentColor] = useState(companySettings?.accent_color ?? '#1E5B94')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const [logoFile, setLogoFile] = useState<File | null>(null)
  const [uploadingLogo, setUploadingLogo] = useState(false)
  const [logoError, setLogoError] = useState<string | null>(null)
  const [logoUploaded, setLogoUploaded] = useState(false)

  async function handleSave(event: React.FormEvent) {
    event.preventDefault()
    if (companySettings === null) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await updateCompanySettings(companySettings.id, { business_name: businessName, accent_color: accentColor })
      await refreshCompanySettings()
      setSaved(true)
    } catch (err) {
      setError(apiErrorMessage(err, t.branding.errorGeneric))
    } finally {
      setSaving(false)
    }
  }

  async function handleUploadLogo() {
    if (companySettings === null || logoFile === null) return
    setUploadingLogo(true)
    setLogoError(null)
    setLogoUploaded(false)
    try {
      await updateCompanyLogo(companySettings.id, logoFile)
      await refreshCompanySettings()
      setLogoFile(null)
      setLogoUploaded(true)
    } catch (err) {
      setLogoError(apiErrorMessage(err, t.branding.logoErrorGeneric))
    } finally {
      setUploadingLogo(false)
    }
  }

  const validColor = HEX_COLOR_PATTERN.test(accentColor)

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold text-ink">{t.branding.title}</h1>
        <p className="mt-2 text-lg text-ink/70">{t.branding.subtitle}</p>
      </div>

      {companySettings === null ? (
        <p className="text-lg text-ink/70">{t.branding.loading}</p>
      ) : (
        <>
            <Card>
              <form onSubmit={(e) => void handleSave(e)} className="flex flex-wrap items-end gap-4">
                <div>
                  <Label htmlFor="business-name">{t.branding.businessName}</Label>
                  <Input
                    id="business-name"
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="accent-color">{t.branding.accentColor}</Label>
                  <div className="flex items-center gap-3">
                    <input
                      aria-hidden="true"
                      tabIndex={-1}
                      type="color"
                      className="h-16 w-16 cursor-pointer rounded-2xl border-2 border-border bg-white"
                      value={validColor ? accentColor : '#1E5B94'}
                      onChange={(e) => setAccentColor(e.target.value)}
                    />
                    <Input
                      id="accent-color"
                      value={accentColor}
                      onChange={(e) => setAccentColor(e.target.value)}
                      className="w-36"
                    />
                  </div>
                </div>
                <Button type="submit" variant="confirm" disabled={saving || !validColor}>
                  {t.branding.save}
                </Button>
              </form>

              {saved && <p className="mt-4 text-lg font-medium text-confirm">{t.branding.saved}</p>}
              {error && (
                <p role="alert" className="mt-4 text-lg font-medium text-cancel">
                  {error}
                </p>
              )}
            </Card>

            <Card>
              <h2 className="mb-4 text-2xl font-bold text-ink">{t.branding.logoTitle}</h2>
              {companySettings.logo ? (
                <img src={companySettings.logo} alt="" className="mb-4 h-24 w-24 rounded-2xl object-cover" />
              ) : (
                <p className="mb-4 text-lg text-ink/70">{t.branding.logoNone}</p>
              )}

              <div className="flex flex-wrap items-center gap-4">
                <Label htmlFor="logo-file" className="mb-0">
                  {t.branding.chooseLogo}
                </Label>
                <input
                  id="logo-file"
                  type="file"
                  accept="image/*"
                  onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)}
                />
                <Button
                  type="button"
                  variant="confirm"
                  disabled={uploadingLogo || logoFile === null}
                  onClick={() => void handleUploadLogo()}
                >
                  {uploadingLogo ? t.branding.uploadingLogo : t.branding.uploadLogo}
                </Button>
              </div>

              {logoUploaded && <p className="mt-4 text-lg font-medium text-confirm">{t.branding.logoUploaded}</p>}
              {logoError && (
                <p role="alert" className="mt-4 text-lg font-medium text-cancel">
                  {logoError}
                </p>
              )}
          </Card>
        </>
      )}
    </div>
  )
}
