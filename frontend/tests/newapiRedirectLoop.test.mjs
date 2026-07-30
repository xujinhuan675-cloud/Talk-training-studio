import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

test('AuthProvider leaves handoff consumption on the LoginPage callback route', () => {
  const source = readSource('src/contexts/AuthContext.tsx')

  assert.match(source, /function isCurrentLoginRoute\(\): boolean/)
  assert.match(source, /window\.location\.pathname === APP_ROUTES\.login/)
  assert.match(source, /isCurrentLoginRoute\(\)\s*\?\s*fetchCurrentAuthSession\(authState\)/s)
})

test('LoginPage consumes the returned handoff code and returns only to a normalized local path', () => {
  const source = readSource('src/pages/LoginPage.tsx')

  assert.match(source, /connectStoredNewApiSession/)
  assert.match(source, /const handoffParams = new URLSearchParams\(location\.search\)/)
  assert.match(source, /handoffParams\.get\('return_to'\)/)
  assert.match(source, /handoffParams\.get\('state'\)/)
  assert.match(source, /normalizeTalkWiseReturnTo/)
  assert.match(source, /<CredentialLoginPanel[^>]+returnTo=\{redirectTarget\}/s)
  assert.doesNotMatch(source, /iframe/)
})

test('all TalkWise login panels use the shared account handoff instead of a password form', () => {
  const panel = readSource('src/components/auth/CredentialLoginPanel.tsx')
  const prompt = readSource('src/components/auth/AuthPromptDialog.tsx')

  assert.match(panel, /buildNewApiLoginUrl/)
  assert.match(panel, /clearNewApiAutoSignInSuppression\(\)/)
  assert.match(panel, /parseNewApiTalkWiseHandoffMessage/)
  assert.match(panel, /window\.addEventListener\('message'/)
  assert.match(panel, /connectNewApiCode\(code, redirectUri, 'session'\)/)
  assert.match(panel, /frameLocation\.origin !== window\.location\.origin/)
  assert.match(panel, /onLoad=\{handleEmbeddedLoad\}/)
  assert.match(panel, /window\.location\.assign\(loginUrl\)/)
  assert.doesNotMatch(panel, /connectNewApiCredentials/)
  assert.doesNotMatch(panel, /passwordInput|usernameInput|login-credential-form/)
  assert.match(prompt, /<CredentialLoginPanel/)
  assert.match(prompt, /returnTo=\{returnTo\}/)
})

test('AuthProvider suppresses automatic browser session recovery after explicit sign out', () => {
  const source = readSource('src/contexts/AuthContext.tsx')

  assert.match(source, /suppressNewApiAutoSignIn/)
  assert.match(source, /const signOut = useCallback[\s\S]*suppressNewApiAutoSignIn\(\)/)
})

test('App keeps its existing public sign-in prompt gate', () => {
  const source = readSource('src/App.tsx')

  assert.match(source, /<AuthPromptDialog \/>/)
  assert.doesNotMatch(source, /function RequireAuthentication/)
})

test('UserMenu opens the shared sign-in prompt when signed out', () => {
  const source = readSource('src/components/layout/UserMenu.tsx')
  const signedOutBranchStart = source.indexOf('if (!currentUser) {')
  const dropdownStart = source.indexOf('return (\n    <DropdownMenu>')
  const signedOutBranch = source.slice(signedOutBranchStart, dropdownStart)

  assert.notEqual(signedOutBranchStart, -1)
  assert.notEqual(dropdownStart, -1)
  assert.match(signedOutBranch, /onClick=\{requestSignIn\}/)
  assert.doesNotMatch(signedOutBranch, /DropdownMenu/)
})
