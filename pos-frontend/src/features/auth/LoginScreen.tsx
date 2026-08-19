import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
import { useAuth } from '@/features/auth/AuthProvider'
import { t } from '@/i18n'

// Corrección de sesión: un solo login, un solo formulario — username y
// email son dos identificadores de la MISMA cuenta y validan contra la
// MISMA contraseña, no dos mecanismos separados. Una ronda anterior
// construyó dos formularios (el segundo con fecha de nacimiento en vez
// de contraseña) que fue un malentendido real y se removió por completo.
export function LoginScreen() {
  const { login, loginError, loggingIn, sessionExpiredNotice } = useAuth()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void login(identifier, password)
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-surface-muted p-6">
      <Card className="w-full max-w-md">
        <h1 className="text-3xl font-bold text-ink">{t.login.title}</h1>
        <p className="mt-2 text-lg text-ink/70">{t.login.subtitle}</p>

        {sessionExpiredNotice && (
          <p role="alert" className="mt-4 text-lg font-medium text-cancel">
            {sessionExpiredNotice}
          </p>
        )}

        <form className="mt-8 flex flex-col gap-6" onSubmit={handleSubmit}>
          <div>
            <Label htmlFor="identifier">{t.login.identifier}</Label>
            <Input
              id="identifier"
              autoComplete="username"
              placeholder={t.login.identifierPlaceholder}
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              required
            />
          </div>

          <div>
            <Label htmlFor="password">{t.login.password}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>

          {loginError && (
            <p role="alert" className="text-lg font-medium text-cancel">
              {loginError}
            </p>
          )}

          <Button type="submit" variant="confirm" size="large" disabled={loggingIn}>
            {loggingIn ? t.login.submitting : t.login.submit}
          </Button>
        </form>
      </Card>
    </div>
  )
}
