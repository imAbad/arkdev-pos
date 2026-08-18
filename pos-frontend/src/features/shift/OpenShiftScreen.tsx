import { useEffect, useState, type FormEvent } from 'react'
import { AppHeader } from '@/components/app-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import { listCashRegisters, openShift } from '@/services/api/salesApi'
import { t } from '@/i18n'
import type { CashRegister, CashShift } from '@/types/api'
import { useAuth } from '@/features/auth/AuthProvider'

interface OpenShiftScreenProps {
  onShiftOpened: (shift: CashShift) => void
}

export function OpenShiftScreen({ onShiftOpened }: OpenShiftScreenProps) {
  const { branch } = useAuth()
  const [registers, setRegisters] = useState<CashRegister[] | null>(null)
  const [registerId, setRegisterId] = useState<number | null>(null)
  const [openingBalance, setOpeningBalance] = useState('0')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listCashRegisters().then((all) => {
      const ownBranchRegisters = branch ? all.filter((register) => register.branch === branch.id) : all
      setRegisters(ownBranchRegisters)
      if (ownBranchRegisters.length > 0) setRegisterId(ownBranchRegisters[0].id)
    })
  }, [branch])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (registerId === null) return
    setSubmitting(true)
    setError(null)
    try {
      const shift = await openShift(registerId, openingBalance)
      onShiftOpened(shift)
    } catch (err) {
      setError(apiErrorMessage(err, t.shift.errorGeneric))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      <AppHeader />
      <div className="flex flex-1 items-center justify-center p-6">
        <Card className="w-full max-w-md">
          <h1 className="text-3xl font-bold text-ink">{t.shift.title}</h1>
          <p className="mt-2 text-lg text-ink/70">{t.shift.subtitle}</p>

          {registers === null ? (
            <p className="mt-8 text-lg text-ink/70">{t.shift.loadingRegisters}</p>
          ) : registers.length === 0 ? (
            <p role="alert" className="mt-8 text-lg font-medium text-cancel">
              {t.shift.noRegisters}
            </p>
          ) : (
            <form className="mt-8 flex flex-col gap-6" onSubmit={handleSubmit}>
              <div>
                <Label htmlFor="register">{t.shift.register}</Label>
                <select
                  id="register"
                  className="h-16 w-full rounded-2xl border-2 border-border bg-white px-5 text-xl text-ink"
                  value={registerId ?? ''}
                  onChange={(event) => setRegisterId(Number(event.target.value))}
                >
                  {registers.map((register) => (
                    <option key={register.id} value={register.id}>
                      {register.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <Label htmlFor="openingBalance">{t.shift.openingBalance}</Label>
                <Input
                  id="openingBalance"
                  type="number"
                  min="0"
                  step="0.01"
                  inputMode="decimal"
                  value={openingBalance}
                  onChange={(event) => setOpeningBalance(event.target.value)}
                  required
                />
              </div>

              {error && (
                <p role="alert" className="text-lg font-medium text-cancel">
                  {error}
                </p>
              )}

              <Button type="submit" variant="confirm" size="large" disabled={submitting}>
                {submitting ? t.shift.submitting : t.shift.submit}
              </Button>
            </form>
          )}
        </Card>
      </div>
    </div>
  )
}
