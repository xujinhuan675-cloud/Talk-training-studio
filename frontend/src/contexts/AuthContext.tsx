import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { APP_ROUTES } from '../appRoutes'
import {
  canAccessManagementFeatures,
  canAccessMemberWorkspace,
  canAccessTeamLeaderboard,
  clearBrowserAuthSession,
  connectNewApiAccessToken,
  connectNewApiAuthorizationCode,
  connectNewApiBrowserSession,
  connectNewApiCredentials as connectNewApiCredentialsService,
  createAuthenticatedState,
  createSignedOutState,
  fetchCurrentAuthSession,
  getMockUsers,
  hasAnySystemRole as authHasAnySystemRole,
  loadInitialAuthState,
  persistAuthState,
  suppressNewApiAutoSignIn,
  type AuthState,
  type AuthStorageScope,
  type AuthUser,
  type MockAuthUser,
  type MockUserId,
  type SystemRole,
} from '../services/auth'

export interface AuthContextValue {
  status: AuthState['status']
  isLoading: boolean
  currentUser: AuthUser | null
  users: MockAuthUser[]
  isAdmin: boolean
  isLeader: boolean
  isStaff: boolean
  canManageTeam: boolean
  canViewTeamLeaderboard: boolean
  canUseMemberWorkspace: boolean
  isSignInPromptOpen: boolean
  requestSignIn: () => void
  closeSignInPrompt: () => void
  requireAuthenticated: () => boolean
  connectNewApiCredentials: (username: string, password: string, scope?: AuthStorageScope) => Promise<AuthUser>
  connectNewApiCode: (code: string, redirectUri?: string | null, scope?: AuthStorageScope) => Promise<AuthUser>
  connectNewApiToken: (accessToken: string, scope?: AuthStorageScope) => Promise<AuthUser>
  connectStoredNewApiSession: () => Promise<AuthState | null>
  refreshSession: () => Promise<AuthState>
  switchUser: (userId: MockUserId, scope?: AuthStorageScope) => void
  signOut: (scope?: AuthStorageScope) => Promise<void>
  hasSystemRole: (role: SystemRole) => boolean
  hasAnySystemRole: (roles: readonly SystemRole[]) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

function isCurrentLoginRoute(): boolean {
  if (typeof window === 'undefined') return false
  return window.location.pathname === APP_ROUTES.login
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>(loadInitialAuthState)
  const [isSignInPromptOpen, setIsSignInPromptOpen] = useState(false)
  const users = useMemo(() => getMockUsers(), [])

  const refreshSession = useCallback(async () => {
    const nextState = await fetchCurrentAuthSession(authState)
    setAuthState(nextState)
    if (nextState.status === 'authenticated' && nextState.provider === 'newapi') {
      persistAuthState(nextState, 'session')
    }
    return nextState
  }, [authState])

  const switchUser = useCallback((userId: MockUserId, scope: AuthStorageScope = 'local') => {
    const nextState = createAuthenticatedState(userId)
    setAuthState(nextState)
    setIsSignInPromptOpen(false)
    persistAuthState(nextState, scope)
  }, [])

  const connectNewApiToken = useCallback(async (accessToken: string, scope: AuthStorageScope = 'session') => {
    const nextState = await connectNewApiAccessToken(accessToken)
    setAuthState(nextState)
    setIsSignInPromptOpen(false)
    persistAuthState(nextState, scope)
    if (!nextState.user) {
      throw new Error('Sign-in session did not return a user')
    }
    return nextState.user
  }, [])

  const connectNewApiCredentials = useCallback(
    async (username: string, password: string, scope: AuthStorageScope = 'session') => {
      const nextState = await connectNewApiCredentialsService(username, password)
      setAuthState(nextState)
      setIsSignInPromptOpen(false)
      persistAuthState(nextState, scope)
      if (!nextState.user) {
        throw new Error('Sign-in session did not return a user')
      }
      return nextState.user
    },
    [],
  )

  const connectNewApiCode = useCallback(
    async (code: string, redirectUri?: string | null, scope: AuthStorageScope = 'session') => {
      const nextState = await connectNewApiAuthorizationCode(code, redirectUri)
      setAuthState(nextState)
      setIsSignInPromptOpen(false)
      persistAuthState(nextState, scope)
      if (!nextState.user) {
        throw new Error('Sign-in session did not return a user')
      }
      return nextState.user
    },
    [],
  )

  const connectStoredNewApiSession = useCallback(async () => {
    const nextState = await connectNewApiBrowserSession()
    if (!nextState) return null
    setAuthState(nextState)
    setIsSignInPromptOpen(false)
    persistAuthState(nextState, 'session')
    return nextState
  }, [])

  const signOut = useCallback(async (scope: AuthStorageScope = 'local') => {
    suppressNewApiAutoSignIn()
    const nextState = createSignedOutState()
    setAuthState(nextState)
    persistAuthState(nextState, scope)
    await clearBrowserAuthSession()
  }, [])

  const requestSignIn = useCallback(() => {
    setIsSignInPromptOpen(true)
  }, [])

  const closeSignInPrompt = useCallback(() => {
    setIsSignInPromptOpen(false)
  }, [])

  const requireAuthenticated = useCallback(() => {
    if (authState.user) return true
    requestSignIn()
    return false
  }, [authState.user, requestSignIn])

  useEffect(() => {
    if (authState.provider !== 'newapi' && authState.status !== 'loading') return
    let cancelled = false
    const browserSession = isCurrentLoginRoute()
      ? fetchCurrentAuthSession(authState)
      : connectNewApiBrowserSession().then((browserState) => browserState ?? fetchCurrentAuthSession(authState))
    void browserSession
      .then((nextState) => {
        if (cancelled) return
        setAuthState(nextState)
        if (nextState.status === 'authenticated' && nextState.provider === 'newapi') {
          setIsSignInPromptOpen(false)
          persistAuthState(nextState, 'session')
        }
      })
      .catch(() => {
        if (cancelled) return
        const nextState = createSignedOutState()
        setAuthState(nextState)
        persistAuthState(nextState, 'session')
      })
    return () => {
      cancelled = true
    }
    // Run once on mount using the stored initial auth state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const hasSystemRole = useCallback(
    (role: SystemRole) => authState.user?.systemRole === role,
    [authState.user?.systemRole],
  )
  const hasAnySystemRole = useCallback(
    (roles: readonly SystemRole[]) => authHasAnySystemRole(authState.user, roles),
    [authState.user],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status: authState.status,
      isLoading: authState.status === 'loading',
      currentUser: authState.user,
      users,
      isAdmin: authState.user?.systemRole === 'admin',
      isLeader: authState.user?.systemRole === 'leader',
      isStaff: authState.user?.systemRole === 'staff',
      canManageTeam: canAccessManagementFeatures(authState.user),
      canViewTeamLeaderboard: canAccessTeamLeaderboard(authState.user),
      canUseMemberWorkspace: canAccessMemberWorkspace(authState.user),
      isSignInPromptOpen,
      requestSignIn,
      closeSignInPrompt,
      requireAuthenticated,
      connectNewApiCredentials,
      connectNewApiCode,
      connectNewApiToken,
      connectStoredNewApiSession,
      refreshSession,
      switchUser,
      signOut,
      hasSystemRole,
      hasAnySystemRole,
    }),
    [
      authState.status,
      authState.user,
      connectNewApiCode,
      connectNewApiCredentials,
      connectNewApiToken,
      connectStoredNewApiSession,
      closeSignInPrompt,
      hasAnySystemRole,
      hasSystemRole,
      isSignInPromptOpen,
      requestSignIn,
      requireAuthenticated,
      refreshSession,
      signOut,
      switchUser,
      users,
    ],
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
