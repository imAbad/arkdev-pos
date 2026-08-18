import { useEffect, useState } from 'react'
import { AppHeader } from '@/components/app-header'
import { Button } from '@/components/ui/button'
import { apiErrorMessage } from '@/lib/api-client'
import { getLowStockProducts } from '@/services/api/catalogApi'
import { useNavigation } from '@/App'
import { t } from '@/i18n'
import type { LowStockRow } from '@/types/api'

/** Punto 7: lista completa detrás del badge del header — accesible a
 * cualquier usuario autenticado (mismo gate que el endpoint, HandlesCash:
 * no exclusivo de admin/supervisor, cualquier cajero que abre turno debe
 * poder ver qué le falta reponer). */
export function LowStockScreen() {
  const { closeLowStock } = useNavigation()
  const [rows, setRows] = useState<LowStockRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getLowStockProducts()
      .then(setRows)
      .catch((err) => setError(apiErrorMessage(err, t.lowStock.errorGeneric)))
  }, [])

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      <AppHeader />

      <div className="flex flex-1 flex-col gap-6 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-ink">{t.lowStock.title}</h1>
            <p className="mt-2 text-lg text-ink/70">{t.lowStock.subtitle}</p>
          </div>
          <Button type="button" variant="neutral" onClick={closeLowStock}>
            {t.lowStock.back}
          </Button>
        </div>

        {error && (
          <p role="alert" className="text-lg font-medium text-cancel">
            {error}
          </p>
        )}

        {!error && rows === null && <p className="text-lg text-ink/70">{t.lowStock.loading}</p>}

        {!error && rows !== null && rows.length === 0 && <p className="text-lg text-ink/70">{t.lowStock.empty}</p>}

        {!error && rows !== null && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-max text-left text-lg">
              <thead>
                <tr className="border-b-2 border-border">
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.lowStock.colProduct}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.lowStock.colSku}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.lowStock.colCurrentStock}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.lowStock.colMinStock}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.product_id} className="border-b border-border">
                    <td className="px-3 py-2">{row.product_name}</td>
                    <td className="px-3 py-2">{row.sku}</td>
                    <td className="px-3 py-2 font-semibold text-warning">{row.current_stock}</td>
                    <td className="px-3 py-2">{row.min_stock}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
