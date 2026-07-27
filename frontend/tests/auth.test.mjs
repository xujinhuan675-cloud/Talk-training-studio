import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTsModule(sourcePath, prefix) {
  const source = fs.readFileSync(path.resolve(sourcePath), 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `${prefix}-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

function createStorage(initialEntries = {}) {
  const entries = new Map(Object.entries(initialEntries))
  return {
    getItem(key) {
      return entries.has(key) ? entries.get(key) : null
    },
    setItem(key, value) {
      entries.set(key, String(value))
    },
    removeItem(key) {
      entries.delete(key)
    },
    has(key) {
      return entries.has(key)
    },
  }
}

test('mock users expose admin, leader, and staff role capabilities', async () => {
  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-roles')

  const admin = auth.getMockUser('admin')
  const leader = auth.getMockUser('leader')
  const sales = auth.getMockUser('sales')
  const customerService = auth.getMockUser('customer_service')

  assert.equal(admin.systemRole, 'admin')
  assert.equal(leader.systemRole, 'leader')
  assert.equal(sales.systemRole, 'staff')
  assert.equal(customerService.systemRole, 'staff')
  assert.equal(auth.canAccessManagementFeatures(admin), true)
  assert.equal(auth.canAccessManagementFeatures(leader), true)
  assert.equal(auth.canAccessManagementFeatures(sales), false)
  assert.equal(auth.canAccessTeamLeaderboard(leader), true)
  assert.equal(auth.canAccessTeamLeaderboard(customerService), false)
  assert.equal(auth.canAccessMemberWorkspace(sales), true)
  assert.equal(auth.hasAnySystemRole(customerService, ['staff']), true)
})

test('NewAPI login defaults to embedded mode for same-page sign-in', async () => {
  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-default-login-mode')

  assert.equal(auth.NEWAPI_LOGIN_MODE, 'embedded')
})

test('stored leader mock user is restored', async () => {
  const localStorage = createStorage({
    'talkwise.auth.state': JSON.stringify({ status: 'authenticated', userId: 'leader' }),
  })
  const sessionStorage = createStorage()
  globalThis.window = { localStorage, sessionStorage }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-leader')
  const initialState = auth.loadInitialAuthState()

  assert.equal(initialState.status, 'authenticated')
  assert.equal(initialState.user.id, 'leader')
  assert.equal(initialState.user.systemRole, 'leader')
  assert.equal(auth.canAccessManagementFeatures(initialState.user), true)
  assert.deepEqual(auth.getAuthRequestHeaders(initialState), {
    'X-Mock-User': 'leader',
    'X-User-Id': 'user-leader-001',
    'X-System-Role': 'leader',
    'X-Team-Id': 'team-revenue',
  })
  assert.deepEqual(auth.getAuthRequestHeaders(auth.createSignedOutState()), {})
})

test('newapi authenticated state uses server session instead of stored bearer token', async () => {
  const localStorage = createStorage()
  const sessionStorage = createStorage()
  globalThis.window = { localStorage, sessionStorage }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-newapi')
  const state = auth.createNewApiAuthenticatedState(
    {
      provider: 'newapi',
      user_id: 'newapi:42',
      username: 'alice',
      display_name: 'Alice Zhang',
      system_role: 'leader',
      business_role: 'sales',
      team_id: 'newapi:paid',
      team_name: 'paid',
      newapi_gateway_base_url: 'https://gateway.example/v1',
      quota_remaining: 900,
      quota_used: 100,
      quota_total: 1000,
      subscription_plan: 'enterprise',
      subscription_status: 'active',
    },
  )

  assert.equal(state.status, 'authenticated')
  assert.equal(state.provider, 'newapi')
  assert.equal(state.user.name, 'Alice Zhang')
  assert.equal(state.user.newapiGatewayBaseUrl, 'https://gateway.example/v1')
  assert.equal(state.user.quotaRemaining, 900)
  assert.equal(state.user.quotaTotal, 1000)
  assert.equal(state.user.subscriptionPlan, 'enterprise')
  assert.deepEqual(auth.getAuthRequestHeaders(state), {})

  auth.persistAuthState(state, 'session')
  assert.equal(sessionStorage.has('talkwise.auth.state'), true)
  assert.equal(localStorage.has('talkwise.auth.state'), false)

  const restored = auth.loadInitialAuthState()
  assert.equal(restored.provider, 'newapi')
  assert.equal(restored.user.userId, 'newapi:42')
  assert.deepEqual(auth.getAuthRequestHeaders(restored), {})
  assert.equal(sessionStorage.getItem('talkwise.auth.state').includes('newapi-token'), false)
})

test('connectNewApiAccessToken exchanges bearer token for a cookie session without persisting it', async () => {
  const localStorage = createStorage()
  const sessionStorage = createStorage()
  globalThis.window = { localStorage, sessionStorage }
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        code: 0,
        message: 'ok',
        data: {
          provider: 'newapi',
          user_id: 'newapi:42',
          username: 'alice',
          display_name: 'Alice Zhang',
          system_role: 'leader',
          business_role: 'sales',
          team_id: 'newapi:paid',
          team_name: 'paid',
        },
      }),
    }
  }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-connect-newapi')
  const state = await auth.connectNewApiAccessToken('newapi-token')
  auth.persistAuthState(state, 'session')

  assert.equal(calls[0].url, '/api/v1/auth/newapi/session')
  assert.equal(calls[0].init.credentials, 'same-origin')
  assert.deepEqual(calls[0].init.headers, { Authorization: 'Bearer newapi-token' })
  assert.equal(state.provider, 'newapi')
  assert.equal(sessionStorage.getItem('talkwise.auth.state').includes('newapi-token'), false)
})

test('connectNewApiAuthorizationCode exchanges a handoff code for a cookie session', async () => {
  const localStorage = createStorage()
  const sessionStorage = createStorage()
  globalThis.window = { localStorage, sessionStorage }
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        code: 0,
        message: 'ok',
        data: {
          provider: 'newapi',
          user_id: 'newapi:88',
          username: 'carol',
          display_name: 'Carol Chen',
          system_role: 'leader',
          business_role: 'sales',
          team_id: 'team-acme',
          team_name: 'Acme Revenue',
          quota_remaining: 900,
          quota_used: 100,
          quota_total: 1000,
          subscription_plan: 'enterprise',
          subscription_status: 'active',
        },
      }),
    }
  }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-connect-newapi-code')
  const state = await auth.connectNewApiAuthorizationCode(
    'handoff-code',
    'https://talkwise.example/login',
  )

  assert.equal(calls[0].url, '/api/v1/auth/newapi/exchange')
  assert.equal(calls[0].init.credentials, 'same-origin')
  assert.deepEqual(calls[0].init.headers, { 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    code: 'handoff-code',
    redirect_uri: 'https://talkwise.example/login',
  })
  assert.equal(state.provider, 'newapi')
  assert.equal(state.user.userId, 'newapi:88')
  assert.equal(state.user.teamName, 'Acme Revenue')
  assert.equal(state.user.quotaRemaining, 900)
})

test('connectNewApiBrowserSession consumes a same-origin NewAPI user token', async () => {
  const localStorage = createStorage({
    user: JSON.stringify({ id: 42, username: 'alice', token: 'same-origin-token', role: 10 }),
  })
  const sessionStorage = createStorage()
  globalThis.window = {
    localStorage,
    sessionStorage,
    location: { origin: 'https://newapi.flowguide.cc', href: 'https://newapi.flowguide.cc/login' },
  }
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        code: 0,
        data: {
          provider: 'newapi',
          user_id: 'newapi:42',
          username: 'alice',
          display_name: 'Alice Zhang',
          system_role: 'leader',
          business_role: 'sales',
        },
      }),
    }
  }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-same-origin-browser-session')
  const state = await auth.connectNewApiBrowserSession()

  assert.equal(auth.canReadSameOriginNewApiStorage(), true)
  assert.equal(state.provider, 'newapi')
  assert.deepEqual(calls[0].init.headers, { Authorization: 'Bearer same-origin-token' })
})

test('NewAPI auto sign-in suppression blocks browser token until cleared', async () => {
  const localStorage = createStorage({
    user: JSON.stringify({ token: 'same-origin-token' }),
  })
  const sessionStorage = createStorage()
  globalThis.window = {
    localStorage,
    sessionStorage,
    location: { origin: 'https://newapi.flowguide.cc', href: 'https://newapi.flowguide.cc/login' },
  }
  let fetchCalled = false
  globalThis.fetch = async () => {
    fetchCalled = true
    return {
      ok: true,
      json: async () => ({
        code: 0,
        data: {
          provider: 'newapi',
          user_id: 'newapi:42',
          username: 'alice',
          system_role: 'leader',
        },
      }),
    }
  }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-suppress-browser-session')
  auth.suppressNewApiAutoSignIn()

  assert.equal(auth.isNewApiAutoSignInSuppressed(), true)
  assert.equal(await auth.connectNewApiBrowserSession(), null)
  assert.equal(fetchCalled, false)

  auth.clearNewApiAutoSignInSuppression()
  const state = await auth.connectNewApiBrowserSession()

  assert.equal(state.provider, 'newapi')
  assert.equal(fetchCalled, true)
})

test('connectNewApiBrowserSession consumes a NewAPI handoff code before token fallback', async () => {
  const localStorage = createStorage({
    user: JSON.stringify({ token: 'same-origin-token' }),
  })
  const sessionStorage = createStorage()
  const historyCalls = []
  globalThis.window = {
    localStorage,
    sessionStorage,
    location: {
      origin: 'https://talkwise.example',
      href: 'https://talkwise.example/login?from=%2Fpractice&talkwise_code=handoff-code&newapi_token=query-token#top',
    },
    history: {
      state: { preserved: true },
      replaceState: (...args) => historyCalls.push(args),
    },
  }
  globalThis.document = { title: 'TalkWise' }
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        code: 0,
        data: {
          provider: 'newapi',
          user_id: 'newapi:88',
          username: 'carol',
          system_role: 'leader',
        },
      }),
    }
  }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-code-browser-session')
  const state = await auth.connectNewApiBrowserSession()

  assert.equal(state.provider, 'newapi')
  assert.equal(calls[0].url, '/api/v1/auth/newapi/exchange')
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    code: 'handoff-code',
    redirect_uri: 'https://talkwise.example/login?from=%2Fpractice#top',
  })
  assert.deepEqual(historyCalls[0], [{ preserved: true }, 'TalkWise', '/login?from=%2Fpractice#top'])
  assert.equal(calls.length, 1)
  delete globalThis.document
})

test('connectNewApiBrowserSession consumes and removes NewAPI token query params', async () => {
  const localStorage = createStorage()
  const sessionStorage = createStorage()
  const historyCalls = []
  globalThis.window = {
    localStorage,
    sessionStorage,
    location: {
      origin: 'https://talkwise.example',
      href: 'https://talkwise.example/login?from=%2Fpractice&newapi_token=query-token#top',
    },
    history: {
      state: { preserved: true },
      replaceState: (...args) => historyCalls.push(args),
    },
  }
  globalThis.document = { title: 'TalkWise' }
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        code: 0,
        data: {
          provider: 'newapi',
          user_id: 'newapi:42',
          username: 'alice',
          system_role: 'leader',
        },
      }),
    }
  }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-query-browser-session')
  const state = await auth.connectNewApiBrowserSession()

  assert.equal(state.provider, 'newapi')
  assert.deepEqual(calls[0].init.headers, { Authorization: 'Bearer query-token' })
  assert.deepEqual(historyCalls[0], [{ preserved: true }, 'TalkWise', '/login?from=%2Fpractice#top'])
  delete globalThis.document
})

test('connectNewApiBrowserSession consumes and removes NewAPI token hash params', async () => {
  const localStorage = createStorage()
  const sessionStorage = createStorage()
  const historyCalls = []
  globalThis.window = {
    localStorage,
    sessionStorage,
    location: {
      origin: 'https://talkwise.example',
      href: 'https://talkwise.example/login#/return?access_token=hash-token&next=%2Fpractice',
    },
    history: {
      state: null,
      replaceState: (...args) => historyCalls.push(args),
    },
  }
  globalThis.document = { title: 'TalkWise' }
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      code: 0,
      data: {
        provider: 'newapi',
        user_id: 'newapi:42',
        username: 'alice',
        system_role: 'leader',
      },
    }),
  })

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-hash-browser-session')
  const state = await auth.connectNewApiBrowserSession()

  assert.equal(state.provider, 'newapi')
  assert.deepEqual(historyCalls[0], [null, 'TalkWise', '/login#/return?next=%2Fpractice'])
  delete globalThis.document
})

test('buildNewApiLoginUrl appends TalkWise return target', async () => {
  const localStorage = createStorage()
  const sessionStorage = createStorage()
  globalThis.window = {
    localStorage,
    sessionStorage,
    location: { origin: 'https://talkwise.example', href: 'https://talkwise.example/review/sessions' },
  }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-login-url')
  const url = new URL(auth.buildNewApiLoginUrl('https://talkwise.example/practice'))

  assert.equal(url.origin, 'https://newapi.flowguide.cc')
  assert.equal(url.pathname, '/login')
  assert.equal(url.searchParams.get('talkwise_return'), 'https://talkwise.example/practice')
  assert.equal(url.searchParams.get('talkwise_redirect_uri'), 'https://talkwise.example/practice')
  assert.equal(url.searchParams.get('talkwise_client_id'), 'talkwise')
})

test('fetchCurrentAuthSession restores a NewAPI user from the HttpOnly session cookie', async () => {
  const localStorage = createStorage()
  const sessionStorage = createStorage()
  globalThis.window = { localStorage, sessionStorage }
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      status: 200,
      json: async () => ({
        code: 0,
        message: 'ok',
        data: {
          provider: 'newapi',
          user_id: 'newapi:42',
          username: 'alice',
          display_name: 'Alice Zhang',
          system_role: 'leader',
          business_role: 'sales',
          team_id: 'newapi:paid',
          team_name: 'paid',
        },
      }),
    }
  }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-fetch-session')
  const state = await auth.fetchCurrentAuthSession(auth.createLoadingAuthState())

  assert.equal(calls[0].url, '/api/v1/auth/me')
  assert.equal(calls[0].init.credentials, 'same-origin')
  assert.deepEqual(calls[0].init.headers, {})
  assert.equal(state.provider, 'newapi')
  assert.equal(state.user.userId, 'newapi:42')
})

test('legacy mock user ids are cleared instead of mapped', async () => {
  const localStorage = createStorage({
    'talkwise.auth.state': JSON.stringify({ status: 'authenticated', userId: 'salesperson' }),
  })
  const sessionStorage = createStorage()
  globalThis.window = { localStorage, sessionStorage }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-legacy')
  const initialState = auth.loadInitialAuthState()

  assert.equal(initialState.status, 'authenticated')
  assert.equal(initialState.user.id, 'admin')
  assert.equal(initialState.user.systemRole, 'admin')
  assert.equal(localStorage.has('talkwise.auth.state'), false)
})

test('corrupt auth storage is cleared', async () => {
  const localStorage = createStorage({
    'talkwise.auth.state': '{not-json',
  })
  const sessionStorage = createStorage()
  globalThis.window = { localStorage, sessionStorage }

  const auth = await loadTsModule('src/services/auth.ts', 'auth-service-corrupt')
  const initialState = auth.loadInitialAuthState()

  assert.equal(initialState.user.id, 'admin')
  assert.equal(localStorage.has('talkwise.auth.state'), false)
})
