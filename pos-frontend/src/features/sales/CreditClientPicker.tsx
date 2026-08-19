import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { formatCurrency } from '@/lib/format'
import { createClient, searchClients } from '@/services/api/customersApi'
import { t } from '@/i18n'
import type { Client } from '@/types/api'

const SEARCH_DEBOUNCE_MS = 300

interface CreditClientPickerProps {
  client: Client | null
  onSelect: (client: Client | null) => void
}

/** Observación de sesión (ronda de 4 piezas, punto 3): venta a crédito —
 * confirmado con evidencia de código que nunca se construyó (PaymentPanel
 * excluía CREDIT a propósito, comentario explícito). El backend
 * (Client/CreditAccount/charge_credit) ya existía completo desde hace
 * varias sesiones; esto es la pantalla que faltaba: buscar o crear un
 * cliente, ver su crédito disponible real (mismo balance que
 * charge_credit valida al cobrar, no una copia de la regla). */
export function CreditClientPicker({ client, onSelect }: CreditClientPickerProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Client[]>([])
  const [searching, setSearching] = useState(false)
  const [showQuickCreate, setShowQuickCreate] = useState(false)

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      return
    }
    setSearching(true)
    const timeout = setTimeout(() => {
      searchClients(query)
        .then(setResults)
        .finally(() => setSearching(false))
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timeout)
  }, [query])

  if (client) {
    return (
      <div className="rounded-2xl border-2 border-border bg-white px-5 py-4">
        <p className="text-lg font-medium text-ink">{client.name}</p>
        <p className="text-base text-ink/70">
          {t.sale.creditAvailable}: {formatCurrency(client.available_credit)}
        </p>
        <Button type="button" variant="neutral" size="compact" className="mt-3" onClick={() => onSelect(null)}>
          {t.sale.creditChangeClient}
        </Button>
      </div>
    )
  }

  if (showQuickCreate) {
    return (
      <QuickCreateClientForm
        onCreated={(created) => {
          onSelect(created)
          setShowQuickCreate(false)
        }}
        onCancel={() => setShowQuickCreate(false)}
      />
    )
  }

  return (
    <div>
      <Label htmlFor="credit-client-search">{t.sale.creditClientLabel}</Label>
      <Input
        id="credit-client-search"
        placeholder={t.sale.creditSearchPlaceholder}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />

      {searching && <p className="mt-2 text-base text-ink/60">{t.sale.creditSearching}</p>}

      {!searching && query.trim() && results.length === 0 && (
        <p role="alert" className="mt-2 text-base text-ink/60">
          {t.sale.creditNoResults}
        </p>
      )}

      {results.length > 0 && (
        <ul className="mt-2 flex flex-col gap-2">
          {results.map((result) => (
            <li key={result.id}>
              <button
                type="button"
                onClick={() => onSelect(result)}
                className="flex w-full items-center justify-between rounded-2xl border-2 border-border bg-white px-4 py-3 text-left hover:bg-surface-muted"
              >
                <span className="text-lg text-ink">{result.name}</span>
                <span className="text-base text-ink/70">{formatCurrency(result.available_credit)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <Button type="button" variant="neutral" size="compact" className="mt-3" onClick={() => setShowQuickCreate(true)}>
        {t.sale.creditNewClient}
      </Button>
    </div>
  )
}

function QuickCreateClientForm({ onCreated, onCancel }: { onCreated: (client: Client) => void; onCancel: () => void }) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const created = await createClient({ name, phone })
      onCreated(created)
    } catch (err) {
      setError(apiErrorMessage(err, t.sale.creditNewClientErrorGeneric))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-col gap-3">
      <div>
        <Label htmlFor="credit-new-client-name">{t.sale.creditNewClientName}</Label>
        <Input id="credit-new-client-name" required value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div>
        <Label htmlFor="credit-new-client-phone">{t.sale.creditNewClientPhone}</Label>
        <Input id="credit-new-client-phone" required value={phone} onChange={(e) => setPhone(e.target.value)} />
      </div>
      <div className="flex gap-3">
        <Button type="submit" variant="confirm" size="compact" disabled={saving}>
          {saving ? t.sale.creditNewClientCreating : t.sale.creditNewClientCreate}
        </Button>
        <Button type="button" variant="neutral" size="compact" onClick={onCancel} disabled={saving}>
          {t.sale.creditNewClientCancel}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-base font-medium text-cancel">
          {error}
        </p>
      )}
    </form>
  )
}
