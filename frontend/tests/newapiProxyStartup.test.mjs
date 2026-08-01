import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

const startDevSource = fs.readFileSync(
  path.resolve('../start-dev.ps1'),
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
