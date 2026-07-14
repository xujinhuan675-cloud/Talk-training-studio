import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTrainingModeModule() {
  const sourcePath = path.resolve('src/services/trainingMode.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `training-mode-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const trainingMode = await loadTrainingModeModule()

test('buildTrainingModeChatPath carries the selected voice mode', () => {
  assert.equal(trainingMode.buildTrainingModeChatPath(42, 'voice'), '/chat/42?trainingMode=voice')
  assert.equal(trainingMode.buildTrainingModeChatPath(42, 'video'), '/chat/42?trainingMode=video')
})

test('buildTrainingModeChatPath carries training mode and training session id', () => {
  const path = trainingMode.buildTrainingModeChatPath(42, 'voice', 'training-session-1')
  const url = new URL(path, 'http://localhost')

  assert.equal(url.pathname, '/chat/42')
  assert.equal(url.searchParams.get('trainingMode'), 'voice')
  assert.equal(url.searchParams.get('trainingSessionId'), 'training-session-1')
})

test('getTrainingModeFromLocation reads valid modes from query first', () => {
  assert.equal(
    trainingMode.getTrainingModeFromLocation('?trainingMode=voice', { trainingMode: 'text' }),
    'voice',
  )
  assert.equal(trainingMode.getTrainingModeFromLocation('?trainingMode=text', null), 'text')
  assert.equal(trainingMode.getTrainingModeFromLocation('?trainingMode=video', null), 'video')
})

test('getTrainingModeFromLocation falls back to route state and rejects invalid modes', () => {
  assert.equal(
    trainingMode.getTrainingModeFromLocation('?trainingMode=invalid', { trainingMode: 'video' }),
    'video',
  )
  assert.equal(trainingMode.getTrainingModeFromLocation('', { trainingMode: 'voice' }), 'voice')
  assert.equal(trainingMode.getTrainingModeFromLocation('?trainingMode=invalid', null), null)
})

test('getTrainingSessionIdFromLocation reads query first and falls back to route state', () => {
  assert.equal(
    trainingMode.getTrainingSessionIdFromLocation('?trainingSessionId=session-from-query', {
      trainingSessionId: 'session-from-state',
    }),
    'session-from-query',
  )
  assert.equal(
    trainingMode.getTrainingSessionIdFromLocation('', { trainingSessionId: ' session-from-state ' }),
    'session-from-state',
  )
  assert.equal(trainingMode.getTrainingSessionIdFromLocation('?trainingSessionId=', null), null)
})

test('isTrainingModeBattlePrep gates voice and video battle prep modes', () => {
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'voice', 'voice'), true)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'video', 'video'), true)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'video', 'voice'), false)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'text', 'video'), false)
  assert.equal(trainingMode.isTrainingModeBattlePrep('private', 'voice', 'voice'), false)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', null, 'voice'), false)
})
