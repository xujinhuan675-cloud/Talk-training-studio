import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

test('AuthProvider defers NewAPI handoff consumption to LoginPage on /login', () => {
  const source = readSource('src/contexts/AuthContext.tsx')

  assert.match(source, /function isCurrentLoginRoute\(\): boolean/)
  assert.match(source, /window\.location\.pathname === APP_ROUTES\.login/)
  assert.match(source, /isCurrentLoginRoute\(\)\s*\?\s*fetchCurrentAuthSession\(authState\)/s)
})

test('AuthProvider suppresses NewAPI auto sign-in on explicit sign out', () => {
  const source = readSource('src/contexts/AuthContext.tsx')

  assert.match(source, /suppressNewApiAutoSignIn/)
  assert.match(source, /const signOut = useCallback[\s\S]*suppressNewApiAutoSignIn\(\)/)
})

test('LoginPage stops automatic redirect after NewAPI auto sign-in errors', () => {
  const source = readSource('src/pages/LoginPage.tsx')

  assert.match(source, /const shouldWaitForAuthSession = canAutoUseNewApi && status === 'loading'/)
  assert.match(source, /error,\s+isAutoConnecting,\s+isRedirectLogin/s)
  assert.match(source, /onClick=\{retryRedirect\}/)
  assert.match(source, /Retry NewAPI sign-in/)
})

test('LoginPage blocks auto sign-in while suppressed and clears it for user-initiated login', () => {
  const source = readSource('src/pages/LoginPage.tsx')

  assert.match(source, /isNewApiAutoSignInSuppressed/)
  assert.match(source, /autoSignInSuppressed/)
  assert.match(source, /const canAutoUseNewApi = NEWAPI_AUTH_ENABLED && !autoSignInSuppressed/)
  assert.match(source, /clearNewApiAutoSignInSuppression\(\)/)
  assert.match(source, /onClick=\{allowNewApiSignIn\}/)
})
