import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTrainingLaunchModule() {
  const sourcePath = path.resolve('src/services/trainingLaunch.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `training-launch-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const trainingLaunch = await loadTrainingLaunchModule()

test('launchTrainingSessionFlow skips battle when payload is null', async () => {
  const events = []
  const result = await trainingLaunch.launchTrainingSessionFlow({
    createTrainingSessionRequest: { mode: 'text', scenario_template_id: 'scenario-1' },
    createTrainingSession: async (request) => {
      events.push(['create', request])
      return { session_id: 'created-1' }
    },
    battlePayload: null,
    startBattle: async () => {
      events.push(['battle'])
      return { id: 'room-from-battle' }
    },
    buildTrainingSessionStartRequest: (data, mode, interactionMode) => {
      events.push(['buildRequest', data, mode, interactionMode])
      return { ...data, runtime: `${mode}:${interactionMode}` }
    },
    startTrainingSession: async (sessionId, request) => {
      events.push(['startSession', sessionId, request])
      return { session_id: 'started-1', room_id: 'room-from-session' }
    },
    trainingMode: 'text',
    interactionMode: 'turn_based',
    buildChatPath: (roomId, mode, sessionId, interactionMode) => {
      events.push(['buildPath', roomId, mode, sessionId, interactionMode])
      return `/conversations/${roomId}?trainingMode=${mode}&interactionMode=${interactionMode}`
    },
    buildNavigationState: ({ room, roomId, startedSession, trainingSession }) => ({
      room,
      roomId,
      startedSession,
      trainingSession,
    }),
    navigate: (to, options) => {
      events.push(['navigate', to, options.state])
    },
    afterStartSession: ({ startedSession }) => {
      events.push(['after', startedSession.session_id])
    },
  })

  assert.deepEqual(events[0], ['create', { mode: 'text', scenario_template_id: 'scenario-1' }])
  assert.equal(events.some(([name]) => name === 'battle'), false)
  assert.deepEqual(events.find(([name]) => name === 'buildRequest'), [
    'buildRequest',
    {},
    'text',
    'turn_based',
  ])
  assert.deepEqual(events.find(([name]) => name === 'startSession'), [
    'startSession',
    'created-1',
    { runtime: 'text:turn_based' },
  ])
  assert.deepEqual(events.find(([name]) => name === 'after'), ['after', 'started-1'])
  assert.deepEqual(events.find(([name]) => name === 'buildPath'), [
    'buildPath',
    'room-from-session',
    'text',
    'started-1',
    'turn_based',
  ])
  assert.deepEqual(events.find(([name]) => name === 'navigate'), [
    'navigate',
    '/conversations/room-from-session?trainingMode=text&interactionMode=turn_based',
    {
      room: null,
      roomId: 'room-from-session',
      startedSession: { session_id: 'started-1', room_id: 'room-from-session' },
      trainingSession: { session_id: 'created-1' },
    },
  ])
  assert.equal(result.room, null)
  assert.equal(result.roomId, 'room-from-session')
  assert.equal(result.chatPath, '/conversations/room-from-session?trainingMode=text&interactionMode=turn_based')
})

test('launchTrainingSessionFlow calls battle when payload exists and falls back to the battle room', async () => {
  const events = []
  const result = await trainingLaunch.launchTrainingSessionFlow({
    createTrainingSessionRequest: { mode: 'voice', scenario_template_id: 'scenario-2' },
    createTrainingSession: async (request) => {
      events.push(['create', request])
      return { session_id: 'created-2' }
    },
    battlePayload: { persona_name: 'Stakeholder' },
    startBattle: async (payload) => {
      events.push(['battle', payload])
      return { id: 42 }
    },
    buildTrainingSessionStartRequest: (data, mode, interactionMode) => {
      events.push(['buildRequest', data, mode, interactionMode])
      return { ...data, runtime: `${mode}:${interactionMode}` }
    },
    startTrainingSession: async (sessionId, request) => {
      events.push(['startSession', sessionId, request])
      return { session_id: 'started-2' }
    },
    trainingMode: 'voice',
    interactionMode: 'realtime',
    buildChatPath: (roomId, mode, sessionId, interactionMode) => {
      events.push(['buildPath', roomId, mode, sessionId, interactionMode])
      return `/conversations/${roomId}?trainingMode=${mode}&interactionMode=${interactionMode}`
    },
    buildNavigationState: ({ room, roomId, startedSession, trainingSession }) => ({
      room,
      roomId,
      startedSession,
      trainingSession,
    }),
    navigate: (to, options) => {
      events.push(['navigate', to, options.state])
    },
  })

  assert.deepEqual(events.find(([name]) => name === 'battle'), ['battle', { persona_name: 'Stakeholder' }])
  assert.deepEqual(events.find(([name]) => name === 'buildRequest'), [
    'buildRequest',
    { room_id: 42 },
    'voice',
    'realtime',
  ])
  assert.deepEqual(events.find(([name]) => name === 'buildPath'), [
    'buildPath',
    42,
    'voice',
    'started-2',
    'realtime',
  ])
  assert.deepEqual(events.find(([name]) => name === 'navigate'), [
    'navigate',
    '/conversations/42?trainingMode=voice&interactionMode=realtime',
    {
      room: { id: 42 },
      roomId: 42,
      startedSession: { session_id: 'started-2' },
      trainingSession: { session_id: 'created-2' },
    },
  ])
  assert.equal(result.roomId, 42)
  assert.equal(result.chatPath, '/conversations/42?trainingMode=voice&interactionMode=realtime')
})
