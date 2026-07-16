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
