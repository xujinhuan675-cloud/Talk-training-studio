import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

const startDevSource = fs.readFileSync(
  path.resolve('../start-dev.ps1'),
  'utf8',
)
const checkDevSource = fs.readFileSync(
  path.resolve('../scripts/check-dev.ps1'),
  'utf8',
)

test('local NewAPI gateway receives the resolved TalkWise backend URL', () => {
  assert.match(
    startDevSource,
    /function Start-LocalNewApiGateway[\s\S]*\[string\]\$TrainingUpstreamUrl/,
  )
  assert.match(
    startDevSource,
    /TALKWISE_TRAINING_UPSTREAM_URL\s*=\s*\$TrainingUpstreamUrl/,
  )
  assert.match(
    startDevSource,
    /Start-LocalNewApiGateway[\s\S]*-TrainingUpstreamUrl \$backendUrl/,
  )
})

test('NewAPI web is the default local frontend host and Vite remains explicit fallback', () => {
  assert.match(startDevSource, /\[switch\]\$LegacyViteFrontend/)
  assert.match(
    startDevSource,
    /function New-NewApiWebCommand[\s\S]*VITE_REACT_APP_SERVER_URL = "\$ServerUrl"/,
  )
  assert.match(
    startDevSource,
    /bun run dev -- --port \$Port --strict-port/,
  )
  assert.match(
    startDevSource,
    /Starting NewAPI web host with Rsbuild[\s\S]*New-NewApiWebCommand -Port \$frontendPort -ServerUrl \$newApiUrl/,
  )
  assert.match(
    startDevSource,
    /NewAPI web same-origin proxy[\s\S]*\$frontendUrl\/api\/status/,
  )
  assert.match(checkDevSource, /\[switch\]\$LegacyViteFrontend/)
  assert.match(
    checkDevSource,
    /NewAPI web same-origin proxy[\s\S]*\$FrontendUrl\/api\/status/,
  )
})
