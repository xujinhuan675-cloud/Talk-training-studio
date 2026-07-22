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

test('launchTrainingSessionFlow starts a session with an empty request by default', async () => {
  const events = []
  const result = await trainingLaunch.launchTrainingSessionFlow({
    createTrainingSessionRequest: { mode: 'text', scenario_template_id: 'scenario-1' },
    createTrainingSession: async (request) => {
      events.push(['create', request])
      return { session_id: 'created-1' }
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
    buildNavigationState: ({ roomId, startedSession, trainingSession }) => ({
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
      roomId: 'room-from-session',
      startedSession: { session_id: 'started-1', room_id: 'room-from-session' },
      trainingSession: { session_id: 'created-1' },
    },
  ])
  assert.equal(result.roomId, 'room-from-session')
  assert.equal(result.chatPath, '/conversations/room-from-session?trainingMode=text&interactionMode=turn_based')
})

test('launchTrainingSessionFlow passes start request data through the training start endpoint', async () => {
  const events = []
  const result = await trainingLaunch.launchTrainingSessionFlow({
    createTrainingSessionRequest: { mode: 'voice', scenario_template_id: 'scenario-2' },
    createTrainingSession: async (request) => {
      events.push(['create', request])
      return { session_id: 'created-2' }
    },
    startRequestData: {
      room_name: 'Scenario practice',
      runtime_persona: {
        name: 'Stakeholder',
        training_points: ['point-1', 'point-2', 'point-3', 'point-4', 'point-5', 'point-6'],
      },
    },
    buildTrainingSessionStartRequest: (data, mode, interactionMode) => {
      events.push(['buildRequest', data, mode, interactionMode])
      return { ...data, runtime: `${mode}:${interactionMode}` }
    },
    startTrainingSession: async (sessionId, request) => {
      events.push(['startSession', sessionId, request])
      return { session_id: 'started-2', room_id: 42 }
    },
    trainingMode: 'voice',
    interactionMode: 'realtime',
    buildChatPath: (roomId, mode, sessionId, interactionMode) => {
      events.push(['buildPath', roomId, mode, sessionId, interactionMode])
      return `/conversations/${roomId}?trainingMode=${mode}&interactionMode=${interactionMode}`
    },
    buildNavigationState: ({ roomId, startedSession, trainingSession }) => ({
      roomId,
      startedSession,
      trainingSession,
    }),
    navigate: (to, options) => {
      events.push(['navigate', to, options.state])
    },
  })

  assert.deepEqual(events.find(([name]) => name === 'buildRequest'), [
    'buildRequest',
    {
      room_name: 'Scenario practice',
      runtime_persona: {
        name: 'Stakeholder',
        training_points: ['point-1', 'point-2', 'point-3', 'point-4', 'point-5', 'point-6'],
      },
    },
    'voice',
    'realtime',
  ])
  assert.deepEqual(events.find(([name]) => name === 'startSession'), [
    'startSession',
    'created-2',
    {
      room_name: 'Scenario practice',
      runtime_persona: {
        name: 'Stakeholder',
        training_points: ['point-1', 'point-2', 'point-3', 'point-4', 'point-5', 'point-6'],
      },
      runtime: 'voice:realtime',
    },
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
      roomId: 42,
      startedSession: { session_id: 'started-2', room_id: 42 },
      trainingSession: { session_id: 'created-2' },
    },
  ])
  assert.equal(result.roomId, 42)
  assert.equal(result.chatPath, '/conversations/42?trainingMode=voice&interactionMode=realtime')
})
