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

test('launchTrainingSessionFlow skips startBattle when no battle payload is provided', async () => {
  const createTrainingSessionRequest = { mode: 'text', scenario_template_id: 'scenario-1' }
  const createTrainingSessionCalls = []
  const startBattleCalls = []
  const startTrainingSessionCalls = []
  const buildRequestCalls = []
  const navigateCalls = []

  const result = await trainingLaunch.launchTrainingSessionFlow({
    createTrainingSessionRequest,
    createTrainingSession: async (request) => {
      createTrainingSessionCalls.push(request)
      return { session_id: 'session-1' }
    },
    battlePayload: null,
    startBattle: async (payload) => {
      startBattleCalls.push(payload)
      throw new Error('startBattle should not be called')
    },
    startTrainingSession: async (sessionId, request) => {
      startTrainingSessionCalls.push({ sessionId, request })
      return { session_id: sessionId, room_id: 41 }
    },
    buildTrainingSessionStartRequest: (request, trainingMode, interactionMode) => {
      buildRequestCalls.push({ request, trainingMode, interactionMode })
      return {
        ...request,
        runtime: trainingMode === 'text' && interactionMode === 'turn_based' ? 'conversation_message_tree' : undefined,
      }
    },
    buildChatPath: (roomId, trainingMode, trainingSessionId, interactionMode) => (
      `/chat/${roomId}?mode=${trainingMode}&session=${trainingSessionId}&interaction=${interactionMode}`
    ),
    buildNavigationState: (context) => ({
      sessionId: context.startedSession.session_id,
      roomId: context.roomId,
      mode: context.trainingMode,
      interactionMode: context.interactionMode,
    }),
    navigate: (pathValue, options) => {
      navigateCalls.push({ pathValue, options })
    },
    trainingMode: 'text',
    interactionMode: 'turn_based',
  })

  assert.deepEqual(createTrainingSessionCalls, [createTrainingSessionRequest])
  assert.deepEqual(startBattleCalls, [])
  assert.deepEqual(startTrainingSessionCalls, [
    {
      sessionId: 'session-1',
      request: { runtime: 'conversation_message_tree' },
    },
  ])
  assert.deepEqual(buildRequestCalls, [
    {
      request: {},
      trainingMode: 'text',
      interactionMode: 'turn_based',
    },
  ])
  assert.deepEqual(navigateCalls, [
    {
      pathValue: '/chat/41?mode=text&session=session-1&interaction=turn_based',
      options: {
        state: {
          sessionId: 'session-1',
          roomId: 41,
          mode: 'text',
          interactionMode: 'turn_based',
        },
      },
    },
  ])
  assert.equal(result.room, null)
  assert.equal(result.roomId, 41)
  assert.equal(result.chatPath, '/chat/41?mode=text&session=session-1&interaction=turn_based')
})

test('launchTrainingSessionFlow calls startBattle and forwards the room id into the start request', async () => {
  const createTrainingSessionRequest = { mode: 'voice', scenario_template_id: 'scenario-2' }
  const createTrainingSessionCalls = []
  const startBattleCalls = []
  const startTrainingSessionCalls = []
  const buildRequestCalls = []
  const navigateCalls = []

  const result = await trainingLaunch.launchTrainingSessionFlow({
    createTrainingSessionRequest,
    createTrainingSession: async (request) => {
      createTrainingSessionCalls.push(request)
      return { session_id: 'session-2' }
    },
    battlePayload: { persona: 'counterpart' },
    startBattle: async (payload) => {
      startBattleCalls.push(payload)
      return { id: 77 }
    },
    startTrainingSession: async (sessionId, request) => {
      startTrainingSessionCalls.push({ sessionId, request })
      return { session_id: sessionId }
    },
    buildTrainingSessionStartRequest: (request, trainingMode, interactionMode) => {
      buildRequestCalls.push({ request, trainingMode, interactionMode })
      return request
    },
    buildChatPath: (roomId, trainingMode, trainingSessionId, interactionMode) => (
      `/chat/${roomId}?mode=${trainingMode}&session=${trainingSessionId}&interaction=${interactionMode}`
    ),
    buildNavigationState: (context) => ({
      sessionId: context.startedSession.session_id,
      roomId: context.roomId,
      roomSeen: context.room?.id ?? null,
      mode: context.trainingMode,
      interactionMode: context.interactionMode,
    }),
    navigate: (pathValue, options) => {
      navigateCalls.push({ pathValue, options })
    },
    trainingMode: 'voice',
    interactionMode: 'realtime',
  })

  assert.deepEqual(createTrainingSessionCalls, [createTrainingSessionRequest])
  assert.deepEqual(startBattleCalls, [{ persona: 'counterpart' }])
  assert.deepEqual(startTrainingSessionCalls, [
    {
      sessionId: 'session-2',
      request: { room_id: 77 },
    },
  ])
  assert.deepEqual(buildRequestCalls, [
    {
      request: { room_id: 77 },
      trainingMode: 'voice',
      interactionMode: 'realtime',
    },
  ])
  assert.deepEqual(navigateCalls, [
    {
      pathValue: '/chat/77?mode=voice&session=session-2&interaction=realtime',
      options: {
        state: {
          sessionId: 'session-2',
          roomId: 77,
          roomSeen: 77,
          mode: 'voice',
          interactionMode: 'realtime',
        },
      },
    },
  ])
  assert.equal(result.room.id, 77)
  assert.equal(result.roomId, 77)
  assert.equal(result.chatPath, '/chat/77?mode=voice&session=session-2&interaction=realtime')
})
