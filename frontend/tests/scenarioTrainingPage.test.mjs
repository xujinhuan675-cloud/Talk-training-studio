import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

test('ScenarioTrainingPage exposes only top-level training modes', () => {
  const source = readSource('src/pages/ScenarioTrainingPage.tsx')
  const match = source.match(/const modeOptions: TrainingMode\[\]\s*=\s*\[([^\]]+)\]/)

  assert.ok(match)
  assert.deepEqual([...match[1].matchAll(/'([^']+)'/g)].map((item) => item[1]), [
    'text',
    'voice',
    'video',
  ])
  assert.doesNotMatch(source, /training\.mode\.realtime\.label/)
  assert.doesNotMatch(source, /useState<ScenarioLaunchMode>/)
})
