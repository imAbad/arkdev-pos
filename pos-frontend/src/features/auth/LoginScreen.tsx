import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
import { useAuth } from '@/features/auth/AuthProvider'
import { t } from '@/i18n'

export function LoginScreen() {
  const { login, loginWithUsername, loginError, loggingIn, sessionExpiredNotice } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [username, setUsername] = useState('')
  const [dateOfBirth, setDateOfBirth] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void login(email, password)
  }

  function handleUsernameSubmit(event: FormEvent) {
    event.preventDefault()
    void loginWithUsername(username, dateOfBirth)
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

          <Button type="submit" variant="confirm" size="large" disabled={loggingIn}>
            {loggingIn ? t.login.submitting : t.login.submit}
          </Button>
        </form>

        <div className="my-6 flex items-center gap-4" aria-hidden="true">
          <div className="h-px flex-1 bg-border" />
          <span className="text-sm font-medium uppercase text-ink/50">{t.login.divider}</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <h2 className="text-xl font-bold text-ink">{t.login.usernameTab}</h2>
        <p className="mt-1 text-base text-ink/70">{t.login.usernameSubtitle}</p>

        <form className="mt-4 flex flex-col gap-6" onSubmit={handleUsernameSubmit}>
          <div>
            <Label htmlFor="login-username">{t.login.username}</Label>
            <Input
              id="login-username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>

          <div>
            <Label htmlFor="login-date-of-birth">{t.login.dateOfBirth}</Label>
            <Input
              id="login-date-of-birth"
              type="date"
              value={dateOfBirth}
              onChange={(event) => setDateOfBirth(event.target.value)}
              required
            />
          </div>

          <Button type="submit" variant="neutral" size="large" disabled={loggingIn}>
            {loggingIn ? t.login.submitting : t.login.usernameSubmit}
          </Button>
        </form>

        {loginError && (
          <p role="alert" className="mt-6 text-lg font-medium text-cancel">
            {loginError}
          </p>
        )}
      </Card>
    </div>
  )
}
