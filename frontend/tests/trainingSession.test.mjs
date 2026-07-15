import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTrainingSessionModule() {
  const sourcePath = path.resolve('src/services/trainingSession.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `training-session-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const trainingSession = await loadTrainingSessionModule()

function installFetchStub(data = { session_id: 'session-1', mode: 'voice', status: 'created' }) {
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({ code: 0, message: 'ok', data }),
    }
  }
  return calls
}

test('createTrainingSession posts to the sessions collection with JSON body', async () => {
  const calls = installFetchStub()
  const body = {
    mode: 'voice',
    scenario_template_id: 'new-customer-discount',
    user_id: 'user-sales-001',
    team_id: 'team-revenue',
    task_config: {
      role: 'Sales Associate',
      level: 'Senior',
      tech_stack: ['discovery'],
      question_type_ratios: { behavioral: 30, craft: 50, pressure: 20 },
      question_count: 5,
      framework: 'prep',
      difficulty: 'medium',
      category: 'sales',
      metadata: {
        source: 'scenario_training',
        scenario_training: { id: 'new-customer-discount' },
      },
    },
  }

  await trainingSession.createTrainingSession(body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(calls[0].init.headers, { 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
})

test('startTrainingSession posts to the start endpoint with JSON body', async () => {
  const calls = installFetchStub()
  const body = { room_id: 42, room_type: 'battle_prep' }

  await trainingSession.startTrainingSession('session-1', body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session-1/start')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
})

test('completeTrainingSession posts to the complete endpoint with JSON body', async () => {
  const calls = installFetchStub()
  const body = { report_id: 501, generate_report: false }

  await trainingSession.completeTrainingSession('session-1', body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session-1/complete')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
})

test('completeTrainingSession posts an empty JSON body by default', async () => {
  const calls = installFetchStub()

  await trainingSession.completeTrainingSession('session-1')

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session-1/complete')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(calls[0].init.headers, { 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(calls[0].init.body), {})
})

test('training session requests surface FastAPI detail string errors', async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 409,
    json: async () => ({ detail: 'training session already completed' }),
  })

  await assert.rejects(
    trainingSession.completeTrainingSession('session-1'),
    /training session already completed/,
  )
})

test('requestTrainingGuidance posts guidance context and returns response data', async () => {
  const data = {
    session_id: 'session 1',
    events: [
      {
        event_type: 'coaching_tip',
        severity: 'info',
        title: 'Ask a follow-up',
        message: 'Probe for measurable impact.',
        suggested_text: 'Can you share the result in numbers?',
        metadata: { rubric_key: 'impact' },
        created_at: '2026-07-14T08:00:00Z',
      },
    ],
  }
  const calls = installFetchStub(data)
  const body = {
    task_goal: 'Practice discovery calls',
    rubric: { impact: 0.4, clarity: 0.6 },
    recent_turns: [
      { speaker: 'candidate', text: 'I improved conversion.', turn_id: 'turn-1' },
      { speaker: 'coach', text: 'What changed after that?' },
    ],
  }

  const result = await trainingSession.requestTrainingGuidance('session 1', body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session%201/guidance')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(calls[0].init.headers, { 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
  assert.deepEqual(result, data)
})

test('getTrainingGuidanceStreamUrl builds an EventSource endpoint', () => {
  const url = trainingSession.getTrainingGuidanceStreamUrl('session 1', {
    message_limit: 25,
    poll_interval_ms: 750,
  })

  assert.equal(
    url,
    '/api/v1/training-studio/sessions/session%201/guidance/stream?message_limit=25&poll_interval_ms=750',
  )
})

test('getTrainingSession and report use GET endpoints without request init', async () => {
  const calls = installFetchStub()

  await trainingSession.getTrainingSession('session 1')
  await trainingSession.getTrainingSessionReport('session-1')

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session%201')
  assert.deepEqual(calls[0].init, {})
  assert.equal(calls[1].url, '/api/v1/training-studio/sessions/session-1/report')
  assert.deepEqual(calls[1].init, {})
})

test('listTrainingSessions uses the sessions collection endpoint', async () => {
  const calls = installFetchStub([])

  await trainingSession.listTrainingSessions()

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions')
  assert.deepEqual(calls[0].init, {})
})
