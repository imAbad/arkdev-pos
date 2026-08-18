import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
import { useAuth } from '@/features/auth/AuthProvider'
import { t } from '@/i18n'

export function LoginScreen() {
  const { login, loginError, loggingIn, sessionExpiredNotice } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void login(email, password)
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
            <Label htmlFor="email">{t.login.email}</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              placeholder={t.login.emailPlaceholder}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
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
