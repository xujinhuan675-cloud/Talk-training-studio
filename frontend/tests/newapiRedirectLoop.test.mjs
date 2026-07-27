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

test('LoginPage delegates to the local credential panel without embedding an external page', () => {
  const source = readSource('src/pages/LoginPage.tsx')

  assert.match(source, /CredentialLoginPanel/)
  assert.match(source, /<main className="login-page"/)
  assert.doesNotMatch(source, /iframe/)
  assert.doesNotMatch(source, /login-newapi-shell/)
  assert.doesNotMatch(source, /login-token-form/)
  assert.doesNotMatch(source, /buildNewApiLoginUrl/)
  assert.doesNotMatch(source, /parseNewApiTalkWiseHandoffMessage/)
})

test('CredentialLoginPanel renders a local credential dialog instead of embedding NewAPI', () => {
  const source = readSource('src/components/auth/CredentialLoginPanel.tsx')

  assert.match(source, /connectNewApiCredentials/)
  assert.match(source, /login-credential-form/)
  assert.match(source, /usernameInput/)
  assert.match(source, /passwordInput/)
  assert.match(source, /用户名或邮箱/)
  assert.match(source, /忘记密码\?/)
  assert.match(source, /没有账户\?/)
  assert.doesNotMatch(source, /iframe/)
  assert.doesNotMatch(source, /login-newapi-shell/)
  assert.doesNotMatch(source, /login-token-form/)
  assert.doesNotMatch(source, /buildNewApiLoginUrl/)
  assert.doesNotMatch(source, /parseNewApiTalkWiseHandoffMessage/)
  assert.doesNotMatch(source, /Opening NewAPI/)
  assert.doesNotMatch(source, /Open NewAPI sign-in/)
  assert.doesNotMatch(source, /NewAPI access token/)
})

test('LoginPage clears suppression before user-initiated credential login', () => {
  const source = readSource('src/components/auth/CredentialLoginPanel.tsx')

  assert.match(source, /isNewApiAutoSignInSuppressed/)
  assert.match(source, /autoSignInSuppressed/)
  assert.match(source, /clearNewApiAutoSignInSuppression\(\)/)
  assert.match(source, /setAutoSignInSuppressed\(false\)/)
  assert.match(source, /connectNewApiCredentials\(username,\s*passwordInput,\s*'session'\)/)
})

test('LoginPage keeps stored session handoff detection without redirecting the browser', () => {
  const source = readSource('src/components/auth/CredentialLoginPanel.tsx')

  assert.match(source, /connectStoredNewApiSession/)
  assert.match(source, /const shouldWaitForAuthSession = NEWAPI_AUTH_ENABLED && status === 'loading'/)
  assert.match(source, /void tryConnectStoredSession\(\)/)
  assert.doesNotMatch(source, /window\.location\.assign/)
  assert.doesNotMatch(source, /redirectStarted/)
})

test('App allows public browsing and mounts the sign-in prompt for gated actions', () => {
  const source = readSource('src/App.tsx')

  assert.match(source, /<AuthPromptDialog \/>/)
  assert.match(source, /<Route element={<AppProvider><Layout \/><\/AppProvider>}>/)
  assert.doesNotMatch(source, /function RequireAuthentication/)
  assert.doesNotMatch(source, /NEWAPI_AUTH_ENABLED && !currentUser/)
  assert.doesNotMatch(source, /<Navigate to={APP_ROUTES\.login}/)
})

test('AuthProvider exposes a local sign-in prompt gate', () => {
  const source = readSource('src/contexts/AuthContext.tsx')

  assert.match(source, /isSignInPromptOpen/)
  assert.match(source, /requestSignIn/)
  assert.match(source, /closeSignInPrompt/)
  assert.match(source, /requireAuthenticated/)
  assert.match(source, /const \[isSignInPromptOpen, setIsSignInPromptOpen\] = useState\(false\)/)
  assert.match(source, /if \(authState\.user\) return true/)
  assert.match(source, /requestSignIn\(\)/)
  assert.match(source, /return false/)
})

test('UserMenu shows a sign-in button instead of a dropdown when signed out', () => {
  const source = readSource('src/components/layout/UserMenu.tsx')
  const css = readSource('src/components/layout/UserMenu.css')
  const signedOutBranchStart = source.indexOf('if (!currentUser) {')
  const dropdownStart = source.indexOf('return (\n    <DropdownMenu>')
  const signedOutBranch = source.slice(signedOutBranchStart, dropdownStart)

  assert.notEqual(signedOutBranchStart, -1)
  assert.notEqual(dropdownStart, -1)
  assert.match(signedOutBranch, /user-menu-trigger user-menu-login/)
  assert.match(signedOutBranch, /onClick=\{requestSignIn\}/)
  assert.match(signedOutBranch, /登录/)
  assert.doesNotMatch(signedOutBranch, /DropdownMenu/)
  assert.doesNotMatch(source, /保持未登录|Stay signed out/)
  assert.match(css, /\.user-menu-login/)
  assert.match(css, /min-width: 72px/)
})

test('Start actions request sign-in instead of redirecting the whole app', () => {
  const homeSource = readSource('src/pages/HomePage.tsx')
  const scenarioSource = readSource('src/pages/ScenarioTrainingPage.tsx')
  const studioSource = readSource('src/pages/TrainingStudioPage.tsx')

  assert.match(homeSource, /const \{ currentUser, requireAuthenticated \} = useAuthContext\(\)/)
  assert.match(homeSource, /if \(!requireAuthenticated\(\)\) return/)
  assert.match(scenarioSource, /requireAuthenticated/)
  assert.match(scenarioSource, /if \(!requireAuthenticated\(\)\) return/)
  assert.match(studioSource, /requireAuthenticated/)
  assert.match(studioSource, /if \(!requireAuthenticated\(\)\) return/)
})
