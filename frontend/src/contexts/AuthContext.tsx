import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'
import {
  createAuthenticatedState,
  createSignedOutState,
  getMockUsers,
  loadInitialAuthState,
  persistAuthState,
  type AuthState,
  type AuthStorageScope,
  type AuthUser,
  type MockUserId,
  type SystemRole,
} from '../services/auth'

export interface AuthContextValue {
  status: AuthState['status']
  currentUser: AuthUser | null
  users: AuthUser[]
  isAdmin: boolean
  switchUser: (userId: MockUserId, scope?: AuthStorageScope) => void
  signOut: (scope?: AuthStorageScope) => void
  hasSystemRole: (role: SystemRole) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>(loadInitialAuthState)
  const users = useMemo(() => getMockUsers(), [])

  const switchUser = useCallback((userId: MockUserId, scope: AuthStorageScope = 'local') => {
    const nextState = createAuthenticatedState(userId)
    setAuthState(nextState)
    persistAuthState(nextState, scope)
  }, [])

  const signOut = useCallback((scope: AuthStorageScope = 'local') => {
    const nextState = createSignedOutState()
    setAuthState(nextState)
    persistAuthState(nextState, scope)
  }, [])

  const hasSystemRole = useCallback(
    (role: SystemRole) => authState.user?.systemRole === role,
    [authState.user?.systemRole],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status: authState.status,
      currentUser: authState.user,
      users,
      isAdmin: authState.user?.systemRole === 'admin',
      switchUser,
      signOut,
      hasSystemRole,
    }),
    [authState.status, authState.user, hasSystemRole, signOut, switchUser, users],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuthContext must be used within an AuthProvider')
  }
  return ctx
}

export default AuthContext
