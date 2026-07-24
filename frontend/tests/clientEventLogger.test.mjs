import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadClientEventLoggerModule() {
  const sourcePath = path.resolve('src/services/clientEventLogger.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  let outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const authSource = fs.readFileSync(path.resolve('src/services/auth.ts'), 'utf8')
  const authOutput = ts.transpileModule(authSource, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(os.tmpdir(), `client-event-logger-${process.pid}-${Date.now()}.mjs`)
  const authPath = path.join(os.tmpdir(), `auth-service-${process.pid}-${Date.now()}.mjs`)
  outputText = outputText.replace("from './auth'", `from '${pathToFileURL(authPath).href}'`)
  fs.writeFileSync(outputPath, outputText)
  fs.writeFileSync(authPath, authOutput)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
    fs.rmSync(authPath, { force: true })
  }
}

const loggerModule = await loadClientEventLoggerModule()

test('sanitizeClientEventPayload removes credentials, transcript text, and raw audio', () => {
  const sanitized = loggerModule.sanitizeClientEventPayload({
    apiKey: 'sk-secret-should-not-appear',
    Authorization: 'Bearer secret-should-not-appear',
    transcript: 'customer transcript should not be logged',
    rawAudio: new ArrayBuffer(8),
    audioBytes: 120,
    sampleRate: 24000,
    nested: {
      phase: 'playback',
      message: 'provider failed with api_key=sk-secret-should-not-appear',
      text: 'assistant transcript should not be logged',
    },
  })

  assert.equal(sanitized.audioBytes, 120)
  assert.equal(sanitized.sampleRate, 24000)
  assert.equal(sanitized.nested.phase, 'playback')
  assert.equal(sanitized.nested.message, 'provider failed with api_key=***')
  assert.equal('apiKey' in sanitized, false)
  assert.equal('Authorization' in sanitized, false)
  assert.equal('transcript' in sanitized, false)
  assert.equal('rawAudio' in sanitized, false)
  assert.equal('text' in sanitized.nested, false)
  assert.equal(JSON.stringify(sanitized).includes('secret-should-not-appear'), false)
  assert.equal(JSON.stringify(sanitized).includes('transcript should not be logged'), false)
})

test('buildRealtimeClientEventRequest bounds oversized payloads and redacts messages', () => {
  const request = loggerModule.buildRealtimeClientEventRequest(
    {
      eventType: 'audio.output_received',
      severity: 'warning',
      trainingSessionId: 'session-1',
      roomId: 42,
      realtimeProfile: 'speech_to_speech',
      message: 'provider failed with sk-secret-should-not-appear',
      payload: {
        status: 'speaking',
        diagnostic: 'x'.repeat(2000),
      },
    },
    { maxPayloadBytes: 300 },
  )

  assert.equal(request.eventType, 'audio.output_received')
  assert.equal(request.severity, 'warning')
  assert.equal(request.trainingSessionId, 'session-1')
  assert.equal(request.roomId, '42')
  assert.equal(request.realtimeProfile, 'speech_to_speech')
  assert.equal(request.message, 'provider failed with sk-***')
  assert.equal(request.payload.truncated, true)
  assert.equal(request.payload.maxPayloadBytes, 300)
  assert.ok(request.payload.payloadBytes > 300)
})

test('logRealtimeClientEvent posts a best-effort event with mock auth headers', async () => {
  const calls = []
  const ok = await loggerModule.logRealtimeClientEvent(
    {
      eventType: 'realtime.start_requested',
      trainingSessionId: 'session-1',
      roomId: 42,
      payload: { latencyProfile: 'near_realtime' },
    },
    {
      fetchFn: async (url, init) => {
        calls.push([url, init])
        return { ok: true }
      },
    },
  )

  assert.equal(ok, true)
  assert.equal(calls.length, 1)
  const [url, init] = calls[0]
  assert.equal(url, loggerModule.CLIENT_REALTIME_EVENT_API)
  assert.equal(init.method, 'POST')
  assert.equal(init.keepalive, true)
  assert.equal(init.headers['Content-Type'], 'application/json')
  assert.equal(init.headers['X-Mock-User'], 'admin')
  assert.deepEqual(JSON.parse(init.body), {
    eventType: 'realtime.start_requested',
    eventCategory: 'realtime_voice',
    severity: 'info',
    provider: 'pipecat',
    payload: { latencyProfile: 'near_realtime' },
    trainingSessionId: 'session-1',
    roomId: '42',
  })
})

test('logRealtimeClientEvent ignores unknown events and network failures', async () => {
  let called = false
  const ignored = await loggerModule.logRealtimeClientEvent(
    { eventType: 'unknown.event', payload: {} },
    {
      fetchFn: async () => {
        called = true
        return { ok: true }
      },
    },
  )
  const failed = await loggerModule.logRealtimeClientEvent(
    { eventType: 'realtime.ws_error', payload: {} },
    {
      fetchFn: async () => {
        throw new Error('network unavailable')
      },
    },
  )

  assert.equal(ignored, false)
  assert.equal(called, false)
  assert.equal(failed, false)
})
