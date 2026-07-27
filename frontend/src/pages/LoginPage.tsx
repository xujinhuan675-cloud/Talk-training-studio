import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import CredentialLoginPanel from '../components/auth/CredentialLoginPanel'
import { useAuthContext } from '../contexts/AuthContext'
import { APP_ROUTES } from '../appRoutes'

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
  const { currentUser } = useAuthContext()
  const location = useLocation()
  const redirectTarget = redirectTargetFromLocation(location.state)

  if (currentUser) {
    return <Navigate to={redirectTarget} replace />
  }

  return (
    <main className="login-page" aria-labelledby="login-page-title">
      <CredentialLoginPanel headingId="login-page-title" />
    </main>
  )
}

export default LoginPage
