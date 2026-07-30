import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

test('public landing preserves the adapted NewAPI section hierarchy without gateway copy', () => {
  const source = readSource('src/pages/PublicLandingPage.tsx')

  assert.match(source, /outside-project\/new-api-main\/web\/src\/features\/home/)
  assert.match(source, /<Hero \/>[\s\S]*<Stats \/>[\s\S]*<Features \/>[\s\S]*<HowItWorks \/>[\s\S]*<CTA \/>/)
  assert.match(source, /function TrainingWorkspacePreview\(\)/)
  assert.match(source, /prefers-reduced-motion: reduce/)
  assert.match(source, /const \{ requestSignIn \} = useAuthContext\(\)/)
  assert.doesNotMatch(source, /to=\{APP_ROUTES\.login\}/)
  assert.doesNotMatch(source, /upstream services integrated|model billing|API Gateway|NewAPI branding/i)
})

test('public product navigation opens the shared sign-in prompt', () => {
  const source = readSource('src/components/layout/PublicProductLayout.tsx')

  assert.match(source, /const \{ requestSignIn \} = useAuthContext\(\)/)
  assert.match(source, /className="public-product-login"[\s\S]*requestSignIn\(\)/)
  assert.doesNotMatch(source, /to=\{APP_ROUTES\.login\}/)
})

test('root landing redirects an authenticated user to the stable workspace route', () => {
  const app = readSource('src/App.tsx')
  const routes = readSource('src/appRoutes.ts')

  assert.match(routes, /workbench: '\/workspace'/)
  assert.match(app, /function PublicLandingRoute\(\)/)
  assert.match(app, /if \(currentUser\) return <Navigate to=\{APP_ROUTES\.workbench\} replace \/>/)
  assert.match(app, /<Route index element=\{<PublicLandingRoute \/>} \/>/)
  assert.match(app, /<Route path="workspace" element=\{<HomePage \/>} \/>/)
})
