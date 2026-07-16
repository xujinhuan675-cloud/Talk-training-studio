export type SystemRole = 'admin' | 'leader' | 'staff'

export type BusinessRole = 'operations' | 'sales' | 'customer_service'

export type MockUserId = 'admin' | 'leader' | 'sales' | 'customer_service'

export type AuthStorageScope = 'local' | 'session'

export type AuthStatus = 'authenticated' | 'signed_out'

export interface AuthUser {
  id: MockUserId
  userId: string
  username: string
  name: string
  systemRole: SystemRole | null
  systemRoleName?: string
  businessRole: BusinessRole
  businessRoleName: string
  teamId: string
  teamName: string
  avatarInitial: string
}

export interface AuthState {
  status: AuthStatus
  user: AuthUser | null
}

interface StoredAuthState {
  status: AuthStatus
  userId?: MockUserId
}

export const AUTH_STORAGE_KEY = 'talkwise.auth.state'

export const MANAGEMENT_SYSTEM_ROLES: readonly SystemRole[] = ['admin', 'leader']

export const MOCK_USERS: readonly AuthUser[] = [
  {
    id: 'admin',
    userId: 'user-admin-001',
    username: 'admin',
    name: 'Admin',
    systemRole: 'admin',
    systemRoleName: 'Admin',
    businessRole: 'operations',
    businessRoleName: 'Operations',
    teamId: 'team-ops',
    teamName: 'Operations Team',
    avatarInitial: 'A',
  },
  {
    id: 'leader',
    userId: 'user-leader-001',
    username: 'leader',
    name: 'Team Lead',
    systemRole: 'leader',
    systemRoleName: 'Leader',
    businessRole: 'sales',
    businessRoleName: 'Sales',
    teamId: 'team-revenue',
    teamName: 'Revenue Team',
    avatarInitial: 'L',
  },
  {
    id: 'sales',
    userId: 'user-sales-001',
    username: 'sales',
    name: 'Sales User',
    systemRole: 'staff',
    systemRoleName: 'Staff',
    businessRole: 'sales',
    businessRoleName: 'Sales',
    teamId: 'team-revenue',
    teamName: 'Revenue Team',
    avatarInitial: 'S',
  },
  {
    id: 'customer_service',
    userId: 'user-cs-001',
    username: 'customer_service',
    name: 'Service User',
    systemRole: 'staff',
    systemRoleName: 'Staff',
    businessRole: 'customer_service',
    businessRoleName: 'Customer Service',
    teamId: 'team-service',
    teamName: 'Service Team',
    avatarInitial: 'C',
  },
]

export const DEFAULT_MOCK_USER_ID: MockUserId = 'admin'

export function getMockUsers(): AuthUser[] {
  return MOCK_USERS.map((user) => ({ ...user }))
}

export function getMockUser(userId: MockUserId): AuthUser {
  const user = MOCK_USERS.find((item) => item.id === userId)
  if (!user) return { ...MOCK_USERS[0] }
  return { ...user }
}

export function getSystemRoleDisplayName(role: SystemRole): string {
  const roleNames: Record<SystemRole, string> = {
    admin: 'Admin',
    leader: 'Leader',
    staff: 'Staff',
  }
  return roleNames[role]
}

export function getUserDisplayRoleName(user: AuthUser): string {
  return user.systemRoleName
    ? `${user.systemRoleName} · ${user.businessRoleName}`
    : user.businessRoleName
}

export function createAuthenticatedState(userId: MockUserId = DEFAULT_MOCK_USER_ID): AuthState {
  return {
    status: 'authenticated',
    user: getMockUser(userId),
  }
}

export function createSignedOutState(): AuthState {
  return {
    status: 'signed_out',
    user: null,
  }
}

export function getAuthRequestHeaders(state: AuthState = loadInitialAuthState()): Record<string, string> {
  const user = state.status === 'authenticated' ? state.user : null
  if (!user) return {}
  return {
    'X-Mock-User': user.id,
    'X-User-Id': user.userId,
    'X-System-Role': user.systemRole ?? '',
    'X-Team-Id': user.teamId,
  }
}

export function hasAnySystemRole(user: AuthUser | null | undefined, roles: readonly SystemRole[]): boolean {
  return Boolean(user?.systemRole && roles.includes(user.systemRole))
}

export function canAccessManagementFeatures(user: AuthUser | null | undefined): boolean {
  return hasAnySystemRole(user, MANAGEMENT_SYSTEM_ROLES)
}

export function canAccessTeamLeaderboard(user: AuthUser | null | undefined): boolean {
  return canAccessManagementFeatures(user)
}

export function canAccessMemberWorkspace(user: AuthUser | null | undefined): boolean {
  return Boolean(user)
}

export function loadInitialAuthState(): AuthState {
  const stored = readStoredAuthState()
  return stored ?? createAuthenticatedState()
}

export function persistAuthState(state: AuthState, scope: AuthStorageScope = 'local'): void {
  if (typeof window === 'undefined') return

  const payload: StoredAuthState = {
    status: state.status,
    userId: state.user?.id,
  }

  try {
    const serialized = JSON.stringify(payload)
    getStorage(scope)?.setItem(AUTH_STORAGE_KEY, serialized)
    getStorage(scope === 'local' ? 'session' : 'local')?.removeItem(AUTH_STORAGE_KEY)
  } catch {
    // Auth persistence is best-effort while the mock service is local-only.
  }
}

function readStoredAuthState(): AuthState | null {
  if (typeof window === 'undefined') return null

  const localState = readFromStorage('local')
  if (localState) return localState

  const sessionState = readFromStorage('session')
  if (sessionState) return sessionState

  return null
}

function readFromStorage(scope: AuthStorageScope): AuthState | null {
  const storage = getStorage(scope)
  if (!storage) return null

  try {
    const raw = storage.getItem(AUTH_STORAGE_KEY)
    if (!raw) return null

    const parsed = JSON.parse(raw) as Partial<StoredAuthState>
    if (parsed.status === 'signed_out') return createSignedOutState()
    const userId = normalizeMockUserId(parsed.userId)
    if (parsed.status === 'authenticated' && userId) {
      return createAuthenticatedState(userId)
    }
    storage.removeItem(AUTH_STORAGE_KEY)
  } catch {
    try {
      storage.removeItem(AUTH_STORAGE_KEY)
    } catch {
      // Storage access can be unavailable in restricted browser contexts.
    }
    return null
  }

  return null
}

function getStorage(scope: AuthStorageScope): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return scope === 'local'
      ? window.localStorage ?? null
      : window.sessionStorage ?? null
  } catch {
    return null
  }
}

function normalizeMockUserId(value: unknown): MockUserId | null {
  if (value === 'admin' || value === 'leader' || value === 'sales' || value === 'customer_service') return value
  return null
}
