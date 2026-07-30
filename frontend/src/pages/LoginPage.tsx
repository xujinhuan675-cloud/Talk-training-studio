import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import CredentialLoginPanel from '../components/auth/CredentialLoginPanel'
import { useAuthContext } from '../contexts/AuthContext'
import { APP_ROUTES } from '../appRoutes'
import { normalizeTalkWiseReturnTo } from '../services/auth'

function redirectTargetFromLocation(state: unknown): string {
  const record = state && typeof state === 'object' ? state as Record<string, unknown> : null
  const from = record?.from
  if (from && typeof from === 'object') {
    const location = from as { pathname?: unknown; search?: unknown }
    const pathname = typeof location.pathname === 'string' ? location.pathname : APP_ROUTES.workbench
    const search = typeof location.search === 'string' ? location.search : ''
    if (pathname !== APP_ROUTES.login) return `${pathname}${search}`
  }
  return APP_ROUTES.workbench
}

const LoginPage: React.FC = () => {
  const { currentUser, connectStoredNewApiSession } = useAuthContext()
  const location = useLocation()
  const handoffParams = new URLSearchParams(location.search)
  const returnTo = handoffParams.get('return_to')
  const handoffState = handoffParams.get('state')
  const redirectTarget = normalizeTalkWiseReturnTo(
    returnTo || handoffState || redirectTargetFromLocation(location.state),
  )
  const [handoffError, setHandoffError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (currentUser) return
    let cancelled = false
    void connectStoredNewApiSession().catch(() => {
      if (!cancelled) setHandoffError('Unable to complete sign-in')
    })
    return () => {
      cancelled = true
    }
  }, [connectStoredNewApiSession, currentUser])

  if (currentUser) {
    return <Navigate to={redirectTarget} replace />
  }

  return (
    <main className="login-page" aria-labelledby="login-page-title">
      <CredentialLoginPanel headingId="login-page-title" returnTo={redirectTarget} />
      {handoffError ? <div className="login-error" role="alert">{handoffError}</div> : null}
    </main>
  )
}

export default LoginPage
