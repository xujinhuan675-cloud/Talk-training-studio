export type SystemRole = 'admin' | 'leader' | 'staff'

export type BusinessRole = 'operations' | 'sales' | 'customer_service'

export type MockUserId = 'admin' | 'leader' | 'sales' | 'customer_service'

export type AuthStorageScope = 'local' | 'session'

export type AuthStatus = 'authenticated' | 'signed_out' | 'loading'

export type AuthProviderKind = 'mock' | 'newapi'

export type NewApiLoginMode = 'external' | 'embedded' | 'redirect'

export interface AuthUser {
  id: string
  authProvider: AuthProviderKind
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
  newapiBaseUrl?: string | null
  newapiGatewayBaseUrl?: string | null
  quotaRemaining?: number | null
  quotaUsed?: number | null
  quotaTotal?: number | null
  requestCount?: number | null
  subscriptionPlan?: string | null
  subscriptionStatus?: string | null
}

export interface MockAuthUser extends AuthUser {
  id: MockUserId
  authProvider: 'mock'
}

export interface NewApiSessionUser {
  provider?: string
  user_id: string
  username?: string | null
  display_name?: string | null
  system_role: string
  business_role?: string | null
  team_id?: string | null
  team_name?: string | null
  newapi_base_url?: string | null
  newapi_group?: string | null
  newapi_gateway_base_url?: string | null
  quota_remaining?: number | null
  quota_used?: number | null
  quota_total?: number | null
  request_count?: number | null
  subscription_plan?: string | null
  subscription_status?: string | null
}

export interface AuthState {
  status: AuthStatus
  provider: AuthProviderKind | null
  user: AuthUser | null
}

interface StoredAuthState {
  status: AuthStatus
  provider?: AuthProviderKind | null
  userId?: MockUserId
  newapiUser?: NewApiSessionUser
}

interface ApiResponse<T> {
  code?: number
  message?: string
  data?: T
}

export const AUTH_STORAGE_KEY = 'talkwise.auth.state'

export const MANAGEMENT_SYSTEM_ROLES: readonly SystemRole[] = ['admin', 'leader']

const DEFAULT_NEWAPI_BASE_URL = 'https://newapi.flowguide.cc'

export const NEWAPI_BASE_URL = readViteEnvValue('VITE_NEWAPI_BASE_URL', DEFAULT_NEWAPI_BASE_URL)
export const NEWAPI_AUTH_ENABLED = readViteEnvBoolean('VITE_NEWAPI_AUTH_ENABLED', false)
export const NEWAPI_LOGIN_URL = readViteEnvValue('VITE_NEWAPI_LOGIN_URL', `${NEWAPI_BASE_URL}/login`)
export const NEWAPI_LOGIN_MODE = normalizeNewApiLoginMode(
  readViteEnvValue('VITE_NEWAPI_LOGIN_MODE', 'external'),
)
export const NEWAPI_CONSOLE_URL = readViteEnvValue('VITE_NEWAPI_CONSOLE_URL', NEWAPI_BASE_URL)
export const NEWAPI_USAGE_URL = readViteEnvValue('VITE_NEWAPI_USAGE_URL', `${NEWAPI_BASE_URL}/usage-logs/common`)
export const NEWAPI_API_KEYS_URL = readViteEnvValue('VITE_NEWAPI_API_KEYS_URL', `${NEWAPI_BASE_URL}/keys`)
export const NEWAPI_TALKWISE_CLIENT_ID = readViteEnvValue('VITE_NEWAPI_TALKWISE_CLIENT_ID', 'talkwise')
export const NEWAPI_TALKWISE_REDIRECT_URI = readViteEnvValue('VITE_NEWAPI_TALKWISE_REDIRECT_URI', '')

const NEWAPI_USER_STORAGE_KEY = 'user'
const NEWAPI_ACCESS_TOKEN_PARAM_NAMES = ['newapi_token', 'access_token', 'token']
const NEWAPI_AUTH_CODE_PARAM_NAMES = ['talkwise_code', 'code']
const NEWAPI_AUTH_STATE_PARAM_NAMES = ['state']

const SYSTEM_ROLE_NAMES: Record<SystemRole, string> = {
  admin: 'Admin',
  leader: 'Leader',
  staff: 'Staff',
}

const BUSINESS_ROLE_NAMES: Record<BusinessRole, string> = {
  operations: 'Operations',
  sales: 'Sales',
  customer_service: 'Customer Service',
}

export const MOCK_USERS: readonly MockAuthUser[] = [
  {
    id: 'admin',
    authProvider: 'mock',
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
    authProvider: 'mock',
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
    authProvider: 'mock',
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
    authProvider: 'mock',
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

export function getMockUsers(): MockAuthUser[] {
  return MOCK_USERS.map((user) => ({ ...user }))
}

export function getMockUser(userId: MockUserId): MockAuthUser {
  const user = MOCK_USERS.find((item) => item.id === userId)
  if (!user) return { ...MOCK_USERS[0] }
  return { ...user }
}

export function getSystemRoleDisplayName(role: SystemRole): string {
  return SYSTEM_ROLE_NAMES[role]
}

export function getUserDisplayRoleName(user: AuthUser): string {
  return user.systemRoleName
    ? `${user.systemRoleName} · ${user.businessRoleName}`
    : user.businessRoleName
}

export function createAuthenticatedState(userId: MockUserId = DEFAULT_MOCK_USER_ID): AuthState {
  return {
    status: 'authenticated',
    provider: 'mock',
    user: getMockUser(userId),
  }
}

export function createNewApiAuthenticatedState(user: NewApiSessionUser): AuthState {
  return {
    status: 'authenticated',
    provider: 'newapi',
    user: createNewApiUser(user),
  }
}

export function createLoadingAuthState(): AuthState {
  return {
    status: 'loading',
    provider: null,
    user: null,
  }
}

export function createSignedOutState(): AuthState {
  return {
    status: 'signed_out',
    provider: null,
    user: null,
  }
}

export function getAuthRequestHeaders(state: AuthState = loadInitialAuthState()): Record<string, string> {
  const user = state.status === 'authenticated' ? state.user : null
  if (!user) return {}
  if (state.provider === 'newapi' || user.authProvider === 'newapi') {
    return {}
  }
  return {
    'X-Mock-User': user.id,
    'X-User-Id': user.userId,
    'X-System-Role': user.systemRole ?? '',
    'X-Team-Id': user.teamId,
  }
}

export async function connectNewApiAccessToken(accessToken: string): Promise<AuthState> {
  const token = accessToken.trim()
  if (!token) {
    throw new Error('NewAPI access token is required')
  }

  const resp = await fetch('/api/v1/auth/newapi/session', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  if (!resp.ok) {
    throw await readAuthError(resp, `Failed to connect NewAPI: ${resp.status}`)
  }

  const json = (await resp.json()) as ApiResponse<NewApiSessionUser>
  if (!json.data) {
    throw new Error(json.message || 'Failed to connect NewAPI')
  }
  return createNewApiAuthenticatedState(json.data)
}

export async function connectNewApiAuthorizationCode(
  code: string,
  redirectUri?: string | null,
): Promise<AuthState> {
  const authorizationCode = code.trim()
  if (!authorizationCode) {
    throw new Error('NewAPI authorization code is required')
  }

  const body = {
    code: authorizationCode,
    redirect_uri: normalizeText(redirectUri) || normalizeText(NEWAPI_TALKWISE_REDIRECT_URI) || undefined,
  }
  const resp = await fetch('/api/v1/auth/newapi/exchange', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    throw await readAuthError(resp, `Failed to exchange NewAPI authorization code: ${resp.status}`)
  }

  const json = (await resp.json()) as ApiResponse<NewApiSessionUser>
  if (!json.data) {
    throw new Error(json.message || 'Failed to exchange NewAPI authorization code')
  }
  return createNewApiAuthenticatedState(json.data)
}

export async function connectNewApiBrowserSession(): Promise<AuthState | null> {
  const handoff = consumeNewApiAuthorizationCodeFromLocation()
  if (handoff) {
    return connectNewApiAuthorizationCode(handoff.code, handoff.redirectUri)
  }

  const accessToken = consumeNewApiAccessTokenFromLocation() || readSameOriginNewApiAccessToken()
  if (!accessToken) return null
  return connectNewApiAccessToken(accessToken)
}

export function buildNewApiLoginUrl(returnTo?: string): string {
  try {
    const url = new URL(NEWAPI_LOGIN_URL)
    const redirectTarget = normalizeText(returnTo) || currentBrowserUrl()
    if (redirectTarget) {
      url.searchParams.set('talkwise_return', redirectTarget)
      url.searchParams.set(
        'talkwise_redirect_uri',
        normalizeText(NEWAPI_TALKWISE_REDIRECT_URI) || redirectTarget,
      )
    }
    url.searchParams.set('talkwise_client_id', NEWAPI_TALKWISE_CLIENT_ID)
    return url.toString()
  } catch {
    return NEWAPI_LOGIN_URL
  }
}

export function canReadSameOriginNewApiStorage(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return new URL(NEWAPI_BASE_URL).origin === window.location.origin
  } catch {
    return false
  }
}

export async function fetchCurrentAuthSession(state: AuthState = loadInitialAuthState()): Promise<AuthState> {
  const resp = await fetch('/api/v1/auth/me', {
    method: 'GET',
    credentials: 'same-origin',
    headers: getAuthRequestHeaders(state),
  })
  if (resp.status === 401 || resp.status === 403) {
    return createSignedOutState()
  }
  if (!resp.ok) {
    throw await readAuthError(resp, `Failed to load auth session: ${resp.status}`)
  }
  const json = (await resp.json()) as ApiResponse<NewApiSessionUser>
  if (!json.data) {
    return createSignedOutState()
  }
  if (json.data.provider === 'newapi') {
    return createNewApiAuthenticatedState(json.data)
  }
  return createAuthenticatedState(normalizeMockUserId(json.data.username) ?? DEFAULT_MOCK_USER_ID)
}

export async function clearBrowserAuthSession(): Promise<void> {
  await fetch('/api/v1/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
  }).catch(() => undefined)
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
  if (stored) return stored
  return NEWAPI_AUTH_ENABLED ? createLoadingAuthState() : createAuthenticatedState()
}

export function persistAuthState(state: AuthState, scope: AuthStorageScope = 'local'): void {
  if (typeof window === 'undefined') return

  const mockUserId = normalizeMockUserId(state.user?.id)
  const payload: StoredAuthState =
    state.status === 'authenticated' && state.provider === 'newapi' && state.user
      ? {
          status: state.status,
          provider: 'newapi',
          newapiUser: toNewApiStoredUser(state.user),
        }
      : {
          status: state.status,
          provider: state.status === 'authenticated' ? 'mock' : null,
          userId: mockUserId ?? undefined,
        }

  try {
    const serialized = JSON.stringify(payload)
    getStorage(scope)?.setItem(AUTH_STORAGE_KEY, serialized)
    getStorage(scope === 'local' ? 'session' : 'local')?.removeItem(AUTH_STORAGE_KEY)
  } catch {
    // Auth persistence is best-effort while local storage may be unavailable.
  }
}

function createNewApiUser(user: NewApiSessionUser): AuthUser {
  const userId = normalizeText(user.user_id) || 'newapi:unknown'
  const username = normalizeText(user.username) || userId
  const displayName = normalizeText(user.display_name) || username
  const systemRole = normalizeSystemRole(user.system_role)
  const businessRole = normalizeBusinessRole(user.business_role)
  const teamId = normalizeText(user.team_id) || 'newapi'
  const teamName = normalizeText(user.team_name) || teamId

  return {
    id: userId,
    authProvider: 'newapi',
    userId,
    username,
    name: displayName,
    systemRole,
    systemRoleName: systemRole ? SYSTEM_ROLE_NAMES[systemRole] : undefined,
    businessRole,
    businessRoleName: BUSINESS_ROLE_NAMES[businessRole],
    teamId,
    teamName,
    avatarInitial: avatarInitialFor(displayName),
    newapiBaseUrl: normalizeText(user.newapi_base_url) || NEWAPI_BASE_URL,
    newapiGatewayBaseUrl: normalizeText(user.newapi_gateway_base_url),
    quotaRemaining: normalizeNullableNumber(user.quota_remaining),
    quotaUsed: normalizeNullableNumber(user.quota_used),
    quotaTotal: normalizeNullableNumber(user.quota_total),
    requestCount: normalizeNullableNumber(user.request_count),
    subscriptionPlan: normalizeText(user.subscription_plan),
    subscriptionStatus: normalizeText(user.subscription_status),
  }
}

function toNewApiStoredUser(user: AuthUser): NewApiSessionUser {
  return {
    provider: 'newapi',
    user_id: user.userId,
    username: user.username,
    display_name: user.name,
    system_role: user.systemRole ?? 'staff',
    business_role: user.businessRole,
    team_id: user.teamId,
    team_name: user.teamName,
    newapi_base_url: user.newapiBaseUrl || NEWAPI_BASE_URL,
    newapi_gateway_base_url: user.newapiGatewayBaseUrl,
    quota_remaining: user.quotaRemaining,
    quota_used: user.quotaUsed,
    quota_total: user.quotaTotal,
    request_count: user.requestCount,
    subscription_plan: user.subscriptionPlan,
    subscription_status: user.subscriptionStatus,
  }
}

function consumeNewApiAuthorizationCodeFromLocation(): { code: string; redirectUri: string } | null {
  if (typeof window === 'undefined') return null

  try {
    const url = new URL(window.location.href)
    const searchCode = authorizationCodeFromSearchParams(url.searchParams)
    const { code: hashCode, nextHash } = authorizationCodeFromHash(url.hash)
    const code = searchCode || hashCode
    if (!code) return null

    NEWAPI_AUTH_CODE_PARAM_NAMES.forEach((name) => {
      url.searchParams.delete(name)
    })
    NEWAPI_AUTH_STATE_PARAM_NAMES.forEach((name) => {
      url.searchParams.delete(name)
    })
    NEWAPI_ACCESS_TOKEN_PARAM_NAMES.forEach((name) => {
      url.searchParams.delete(name)
    })
    url.hash = removeSensitiveHandoffParamsFromHash(nextHash)

    const redirectUri = `${url.origin}${url.pathname}${url.search}${url.hash}`
    const nextUrl = `${url.pathname}${url.search}${url.hash}`
    const pageTitle = typeof document === 'undefined' ? '' : document.title
    window.history?.replaceState?.(window.history.state, pageTitle, nextUrl)
    return { code, redirectUri }
  } catch {
    return null
  }
}

function consumeNewApiAccessTokenFromLocation(): string | null {
  if (typeof window === 'undefined') return null

  try {
    const url = new URL(window.location.href)
    const searchToken = accessTokenFromSearchParams(url.searchParams)
    const { token: hashToken, nextHash } = accessTokenFromHash(url.hash)
    const accessToken = searchToken || hashToken
    if (!accessToken) return null

    NEWAPI_ACCESS_TOKEN_PARAM_NAMES.forEach((name) => {
      url.searchParams.delete(name)
    })
    NEWAPI_AUTH_CODE_PARAM_NAMES.forEach((name) => {
      url.searchParams.delete(name)
    })
    url.hash = removeSensitiveHandoffParamsFromHash(nextHash)

    const nextUrl = `${url.pathname}${url.search}${url.hash}`
    const pageTitle = typeof document === 'undefined' ? '' : document.title
    window.history?.replaceState?.(window.history.state, pageTitle, nextUrl)
    return accessToken
  } catch {
    return null
  }
}

function readSameOriginNewApiAccessToken(): string | null {
  if (!canReadSameOriginNewApiStorage()) return null
  try {
    const raw = window.localStorage?.getItem(NEWAPI_USER_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { token?: unknown; access_token?: unknown }
    return normalizeText(parsed.token) || normalizeText(parsed.access_token)
  } catch {
    return null
  }
}

function accessTokenFromSearchParams(params: URLSearchParams): string | null {
  for (const name of NEWAPI_ACCESS_TOKEN_PARAM_NAMES) {
    const value = normalizeText(params.get(name))
    if (value) return value
  }
  return null
}

function authorizationCodeFromSearchParams(params: URLSearchParams): string | null {
  for (const name of NEWAPI_AUTH_CODE_PARAM_NAMES) {
    const value = normalizeText(params.get(name))
    if (value) return value
  }
  return null
}

function accessTokenFromHash(hash: string): { token: string | null; nextHash: string } {
  const rawHash = hash.startsWith('#') ? hash.slice(1) : hash
  if (!rawHash) return { token: null, nextHash: hash }

  const separatorIndex = rawHash.indexOf('?')
  const prefix = separatorIndex >= 0 ? rawHash.slice(0, separatorIndex) : ''
  const paramText = separatorIndex >= 0 ? rawHash.slice(separatorIndex + 1) : rawHash
  const params = new URLSearchParams(paramText)
  const token = accessTokenFromSearchParams(params)
  if (!token) return { token: null, nextHash: hash }

  NEWAPI_ACCESS_TOKEN_PARAM_NAMES.forEach((name) => {
    params.delete(name)
  })
  const nextParamText = params.toString()
  if (prefix) {
    return { token, nextHash: nextParamText ? `#${prefix}?${nextParamText}` : `#${prefix}` }
  }
  return { token, nextHash: nextParamText ? `#${nextParamText}` : '' }
}

function authorizationCodeFromHash(hash: string): { code: string | null; nextHash: string } {
  const rawHash = hash.startsWith('#') ? hash.slice(1) : hash
  if (!rawHash) return { code: null, nextHash: hash }

  const separatorIndex = rawHash.indexOf('?')
  const prefix = separatorIndex >= 0 ? rawHash.slice(0, separatorIndex) : ''
  const paramText = separatorIndex >= 0 ? rawHash.slice(separatorIndex + 1) : rawHash
  const params = new URLSearchParams(paramText)
  const code = authorizationCodeFromSearchParams(params)
  if (!code) return { code: null, nextHash: hash }

  NEWAPI_AUTH_CODE_PARAM_NAMES.forEach((name) => {
    params.delete(name)
  })
  NEWAPI_AUTH_STATE_PARAM_NAMES.forEach((name) => {
    params.delete(name)
  })
  const nextParamText = params.toString()
  if (prefix) {
    return { code, nextHash: nextParamText ? `#${prefix}?${nextParamText}` : `#${prefix}` }
  }
  return { code, nextHash: nextParamText ? `#${nextParamText}` : '' }
}

function removeSensitiveHandoffParamsFromHash(hash: string): string {
  const rawHash = hash.startsWith('#') ? hash.slice(1) : hash
  if (!rawHash) return hash

  const separatorIndex = rawHash.indexOf('?')
  const prefix = separatorIndex >= 0 ? rawHash.slice(0, separatorIndex) : ''
  const paramText = separatorIndex >= 0 ? rawHash.slice(separatorIndex + 1) : rawHash
  const params = new URLSearchParams(paramText)
  let changed = false

  for (const name of [
    ...NEWAPI_AUTH_CODE_PARAM_NAMES,
    ...NEWAPI_AUTH_STATE_PARAM_NAMES,
    ...NEWAPI_ACCESS_TOKEN_PARAM_NAMES,
  ]) {
    if (params.has(name)) changed = true
    params.delete(name)
  }
  if (!changed) return hash

  const nextParamText = params.toString()
  if (prefix) return nextParamText ? `#${prefix}?${nextParamText}` : `#${prefix}`
  return nextParamText ? `#${nextParamText}` : ''
}

function currentBrowserUrl(): string | undefined {
  if (typeof window === 'undefined') return undefined
  return window.location.href
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
    if (parsed.status === 'authenticated' && parsed.provider === 'newapi') {
      if (parsed.newapiUser) {
        return createNewApiAuthenticatedState(parsed.newapiUser)
      }
      storage.removeItem(AUTH_STORAGE_KEY)
      return null
    }

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

function normalizeSystemRole(value: unknown): SystemRole | null {
  if (value === 'admin' || value === 'leader' || value === 'staff') return value
  return null
}

function normalizeBusinessRole(value: unknown): BusinessRole {
  if (value === 'operations' || value === 'sales' || value === 'customer_service') return value
  return 'sales'
}

function normalizeText(value: unknown): string | null {
  if (value === undefined || value === null) return null
  const text = String(value).trim()
  return text || null
}

function normalizeNullableNumber(value: unknown): number | null {
  if (value === undefined || value === null || value === '') return null
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

function avatarInitialFor(value: string): string {
  return value.trim().charAt(0).toUpperCase() || 'N'
}

async function readAuthError(resp: Response, fallback: string): Promise<Error> {
  const json = await resp.json().catch(() => null)
  const message =
    (typeof json?.message === 'string' && json.message) ||
    (typeof json?.detail === 'string' && json.detail) ||
    fallback
  return new Error(message)
}

function readViteEnvValue(name: string, fallback: string): string {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
  return env?.[name] || fallback
}

function readViteEnvBoolean(name: string, fallback: boolean): boolean {
  const raw = readViteEnvValue(name, String(fallback)).trim().toLowerCase()
  if (['1', 'true', 'yes', 'on'].includes(raw)) return true
  if (['0', 'false', 'no', 'off'].includes(raw)) return false
  return fallback
}

function normalizeNewApiLoginMode(value: string): NewApiLoginMode {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'embedded' || normalized === 'redirect') return normalized
  return 'external'
}
