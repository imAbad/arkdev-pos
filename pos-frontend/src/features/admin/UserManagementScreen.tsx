import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiErrorMessage } from '@/lib/api-client'
import {
  createUser,
  deactivateUser,
  listBranches,
  listUsers,
  reactivateUser,
} from '@/services/api/tenantsApi'
import { t } from '@/i18n'
import type { Branch, Role, UserProfile } from '@/types/api'

/** Punto 9 (el de mayor riesgo de la sesión): pantalla de gestión de
 * usuarios, ADMINISTRADOR exclusivo — el backend ya rechaza a cualquier
 * otro rol (core.permissions.IsAdministrator en UserProfileViewSet), acá
 * solo se refleja con el link del sidebar (ADMIN-only, igual que
 * Módulos). */
export function UserManagementScreen() {
  const [users, setUsers] = useState<UserProfile[] | null>(null)
  const [branches, setBranches] = useState<Branch[]>([])
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<number | null>(null)

  function load() {
    setError(null)
    Promise.all([listUsers(), listBranches()])
      .then(([usersResult, branchesResult]) => {
        setUsers(usersResult)
        setBranches(branchesResult)
      })
      .catch((err) => setError(apiErrorMessage(err, t.users.errorGeneric)))
  }

  useEffect(load, [])

  function branchName(branchId: number): string {
    return branches.find((b) => b.id === branchId)?.name ?? `#${branchId}`
  }

  async function handleDeactivate(profile: UserProfile) {
    setActionError(null)
    setPendingId(profile.id)
    try {
      const updated = await deactivateUser(profile.id)
      setUsers((prev) => prev?.map((u) => (u.id === updated.id ? updated : u)) ?? null)
    } catch (err) {
      setActionError(apiErrorMessage(err, t.users.deactivateErrorGeneric))
    } finally {
      setPendingId(null)
    }
  }

  async function handleReactivate(profile: UserProfile) {
    setActionError(null)
    setPendingId(profile.id)
    try {
      const updated = await reactivateUser(profile.id)
      setUsers((prev) => prev?.map((u) => (u.id === updated.id ? updated : u)) ?? null)
    } catch (err) {
      setActionError(apiErrorMessage(err, t.users.reactivateErrorGeneric))
    } finally {
      setPendingId(null)
    }
  }

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold text-ink">{t.users.title}</h1>
        <p className="mt-2 text-lg text-ink/70">{t.users.subtitle}</p>
      </div>

      <NewUserForm branches={branches} onCreated={load} />

      {error && (
        <p role="alert" className="text-lg font-medium text-cancel">
          {error}
        </p>
      )}
      {actionError && (
        <p role="alert" className="text-lg font-medium text-cancel">
          {actionError}
        </p>
      )}

        {!error && users === null && <p className="text-lg text-ink/70">{t.users.loading}</p>}

        {!error && users !== null && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-max text-left text-lg">
              <thead>
                <tr className="border-b-2 border-border">
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.users.colEmail}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.users.colRole}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.users.colBranch}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.users.colCapabilities}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{t.users.colStatus}</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold text-ink" />
                </tr>
              </thead>
              <tbody>
                {users.map((profile) => (
                  <tr key={profile.id} className="border-b border-border">
                    <td className="px-3 py-2">{profile.email}</td>
                    <td className="px-3 py-2">{profile.role === 'ADMINISTRADOR' ? t.users.roleAdministrador : t.users.roleCajero}</td>
                    <td className="px-3 py-2">{branchName(profile.branch)}</td>
                    <td className="px-3 py-2">
                      {[
                        profile.capabilities.handles_cash && t.users.capabilityHandlesCash,
                        profile.capabilities.can_authorize_exceptions && t.users.capabilityCanAuthorize,
                      ]
                        .filter(Boolean)
                        .join(' · ') || '—'}
                    </td>
                    <td className={`px-3 py-2 font-semibold ${profile.is_active ? 'text-confirm' : 'text-cancel'}`}>
                      {profile.is_active ? t.users.statusActive : t.users.statusInactive}
                    </td>
                    <td className="px-3 py-2">
                      {profile.is_active ? (
                        <Button
                          type="button"
                          variant="cancel"
                          size="compact"
                          disabled={pendingId === profile.id}
                          onClick={() => void handleDeactivate(profile)}
                        >
                          {t.users.deactivate}
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          variant="confirm"
                          size="compact"
                          disabled={pendingId === profile.id}
                          onClick={() => void handleReactivate(profile)}
                        >
                          {t.users.reactivate}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
        </div>
      )}
    </div>
  )
}

function NewUserForm({ branches, onCreated }: { branches: Branch[]; onCreated: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('CAJERO')
  const [branchId, setBranchId] = useState<number | ''>('')
  const [handlesCash, setHandlesCash] = useState(false)
  const [canAuthorizeExceptions, setCanAuthorizeExceptions] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createdNotice, setCreatedNotice] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (branchId === '') return
    setSaving(true)
    setError(null)
    setCreatedNotice(false)
    try {
      await createUser({
        email,
        password,
        branch: branchId,
        role,
        capabilities: { handles_cash: handlesCash, can_authorize_exceptions: canAuthorizeExceptions },
      })
      setEmail('')
      setPassword('')
      setHandlesCash(false)
      setCanAuthorizeExceptions(false)
      setCreatedNotice(true)
      onCreated()
    } catch (err) {
      setError(apiErrorMessage(err, t.users.createErrorGeneric))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <h2 className="mb-4 text-2xl font-bold text-ink">{t.users.newUserTitle}</h2>
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-4">
        <div>
          <Label htmlFor="new-user-email">{t.users.email}</Label>
          <Input id="new-user-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="new-user-password">{t.users.password}</Label>
          <Input
            id="new-user-password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="new-user-branch">{t.users.branch}</Label>
          <select
            id="new-user-branch"
            required
            className="h-16 rounded-2xl border-2 border-border bg-white px-5 text-xl text-ink"
            value={branchId}
            onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="" disabled>
              —
            </option>
            {branches.map((branch) => (
              <option key={branch.id} value={branch.id}>
                {branch.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="new-user-role">{t.users.role}</Label>
          <select
            id="new-user-role"
            className="h-16 rounded-2xl border-2 border-border bg-white px-5 text-xl text-ink"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            <option value="CAJERO">{t.users.roleCajero}</option>
            <option value="ADMINISTRADOR">{t.users.roleAdministrador}</option>
          </select>
        </div>

        {role === 'CAJERO' && (
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 text-lg text-ink">
              <input type="checkbox" checked={handlesCash} onChange={(e) => setHandlesCash(e.target.checked)} />
              {t.users.handlesCash}
            </label>
            <label className="flex items-center gap-2 text-lg text-ink">
              <input
                type="checkbox"
                checked={canAuthorizeExceptions}
                onChange={(e) => setCanAuthorizeExceptions(e.target.checked)}
              />
              {t.users.canAuthorizeExceptions}
            </label>
          </div>
        )}

        <Button type="submit" variant="confirm" disabled={saving}>
          {t.users.create}
        </Button>
      </form>

      {createdNotice && <p className="mt-4 text-lg font-medium text-confirm">{t.users.createdNotice}</p>}
      {error && (
        <p role="alert" className="mt-4 text-lg font-medium text-cancel">
          {error}
        </p>
      )}
    </Card>
  )
}
