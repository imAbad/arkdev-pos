import { useEffect, useState } from 'react'
import { AuthProvider, useAuth } from '@/features/auth/AuthProvider'
import { LoginScreen } from '@/features/auth/LoginScreen'
import { OpenShiftScreen } from '@/features/shift/OpenShiftScreen'
import { SaleScreen } from '@/features/sales/SaleScreen'
import { getCurrentShift } from '@/services/api/salesApi'
import { t } from '@/i18n'
import type { CashShift } from '@/types/api'

function AppScreens() {
  const { status } = useAuth()
  const [shift, setShift] = useState<CashShift | null | 'loading'>('loading')

  useEffect(() => {
    if (status !== 'authenticated') return
    setShift('loading')
    getCurrentShift().then(setShift)
  }, [status])

  if (status === 'loading') {
    return <FullScreenMessage message={t.common.loading} />
  }

  if (status === 'unauthenticated') {
    return <LoginScreen />
  }

  if (shift === 'loading') {
    return <FullScreenMessage message={t.common.loading} />
  }

  if (shift === null) {
    return <OpenShiftScreen onShiftOpened={setShift} />
  }

  return <SaleScreen shift={shift} />
}

function FullScreenMessage({ message }: { message: string }) {
  return (
    <div className="flex min-h-svh items-center justify-center bg-surface-muted">
      <p className="text-xl text-ink/70">{message}</p>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppScreens />
    </AuthProvider>
  )
}
