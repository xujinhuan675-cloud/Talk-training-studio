import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadRealtimeSessionModule() {
  const sourcePath = path.resolve('src/services/realtimeSession.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  let outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(os.tmpdir(), `realtime-session-${process.pid}-${Date.now()}.mjs`)
  const cleanupPaths = [outputPath]
  if (outputText.includes("from './auth'")) {
    const authSource = fs.readFileSync(path.resolve('src/services/auth.ts'), 'utf8')
    const authOutput = ts.transpileModule(authSource, {
      compilerOptions: {
        module: ts.ModuleKind.ES2022,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText
    const authPath = path.join(os.tmpdir(), `auth-service-${process.pid}-${Date.now()}.mjs`)
    fs.writeFileSync(authPath, authOutput)
    cleanupPaths.push(authPath)
    outputText = outputText.replace("from './auth'", `from '${pathToFileURL(authPath).href}'`)
  }
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    cleanupPaths.forEach((item) => fs.rmSync(item, { force: true }))
  }
}

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  constructor(url, protocols) {
    this.url = url
    this.protocols = protocols
    this.readyState = FakeWebSocket.CONNECTING
    this.sent = []
    this.binaryType = ''
    this.onopen = null
    this.onmessage = null
    this.onerror = null
    this.onclose = null
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  send(data) {
    this.sent.push(data)
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }
}

globalThis.window = {
  location: {
    protocol: 'https:',
    host: 'demo.example',
  },
}
globalThis.WebSocket = FakeWebSocket
globalThis.atob ??= (value) => Buffer.from(value, 'base64').toString('binary')

const realtimeSession = await loadRealtimeSessionModule()

test('getTrainingRealtimeWebSocketUrl builds a bound training realtime endpoint', () => {
  const url = realtimeSession.getTrainingRealtimeWebSocketUrl({
    sessionId: 'session 1',
    roomId: 42,
    provider: 'openai',
    audioFormat: 'pcm16',
  })

  assert.equal(
    url,
    'wss://demo.example/api/v1/training-studio/realtime?session_id=session+1&room_id=42&provider=pipecat&audio_format=pcm16',
  )
})

test('getTrainingRealtimeWebSocketUrl appends non-default realtime voice profiles', () => {
  const url = realtimeSession.getTrainingRealtimeWebSocketUrl({
    sessionId: 'session-1',
    roomId: 42,
    audioFormat: 'pcm16',
    profile: 'speech_to_speech',
  })

  assert.equal(
    url,
    'wss://demo.example/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat&audio_format=pcm16&profile=speech_to_speech',
  )
})

test('getRealtimeVoiceAudioContract keeps cascade at 16k and true realtime at 24k', () => {
  assert.deepEqual(realtimeSession.getRealtimeVoiceAudioContract(), {
    realtimeProfile: 'cascade',
    canonicalProfile: 'cascade',
    inputSampleRate: 16000,
    outputSampleRate: 24000,
    channels: 1,
    audioFormat: 'pcm16',
    inputMimeType: 'audio/pcm',
    transport: 'websocket',
    latencyProfile: 'near_realtime',
    turnDetection: 'local_vad',
  })

  assert.deepEqual(realtimeSession.getRealtimeVoiceAudioContract('true_realtime'), {
    realtimeProfile: 'true_realtime',
    canonicalProfile: 'speech_to_speech',
    inputSampleRate: 24000,
    outputSampleRate: 24000,
    channels: 1,
    audioFormat: 'pcm16',
    inputMimeType: 'audio/pcm',
    transport: 'websocket',
    latencyProfile: 'true_realtime',
    turnDetection: 'server_semantic_vad',
  })
})

test('RealtimeSession sends session control events as JSON frames', () => {
  let socket
  const statuses = []
  const client = realtimeSession.createRealtimeSession({
    url: 'ws://local/realtime',
    socketFactory: (url, protocols) => {
      socket = new FakeWebSocket(url, protocols)
      return socket
    },
    onStatusChange: (status) => statuses.push(status),
  })

  client.connect()
  socket.open()
  client.send({
    type: 'session.configure',
    sessionId: 'session-1',
    roomId: 42,
  })

  assert.deepEqual(statuses, ['connecting', 'connected'])
  assert.equal(socket.url, 'ws://local/realtime')
  assert.deepEqual(JSON.parse(socket.sent[0]), {
    type: 'session.configure',
    sessionId: 'session-1',
    roomId: 42,
  })
})

test('RealtimeSession sends audio chunks as binary frames and commit as JSON', () => {
  let socket
  const client = realtimeSession.createRealtimeSession({
    url: 'ws://local/realtime',
    socketFactory: () => {
      socket = new FakeWebSocket('ws://local/realtime')
      return socket
    },
  })

  const audio = new ArrayBuffer(4)
  client.connect()
  socket.open()
  client.send({ type: 'audio.input', audio, mimeType: 'audio/pcm', sequence: 1 })
  client.send({ type: 'audio.commit' })

  assert.equal(socket.sent[0], audio)
  assert.deepEqual(JSON.parse(socket.sent[1]), { type: 'audio.commit' })
})

test('RealtimeSession updates status from backend wire events', () => {
  let socket
  const events = []
  const statuses = []
  const client = realtimeSession.createRealtimeSession({
    url: 'ws://local/realtime',
    socketFactory: () => {
      socket = new FakeWebSocket('ws://local/realtime')
      return socket
    },
    onStatusChange: (status) => statuses.push(status),
    onEvent: (event) => events.push(event),
  })

  client.connect()
  socket.open()
  socket.onmessage?.({
    data: JSON.stringify({
      type: 'transcript.persisted',
      sessionId: 'session-1',
      status: 'listening',
      payload: {
        trainingSessionId: 'session-1',
        roomId: 42,
        message: {
          id: 1,
          room_id: 42,
          content: 'Saved turn.',
          sender_type: 'user',
          sender_id: 'user',
        },
      },
    }),
  })

  assert.equal(statuses.at(-1), 'listening')
  assert.equal(events[0].type, 'transcript.persisted')
  assert.equal(events[0].payload.message.content, 'Saved turn.')
})

test('decodeRealtimeServerEvent normalizes nested realtime error payloads', () => {
  const event = realtimeSession.decodeRealtimeServerEvent(JSON.stringify({
    type: 'error',
    sessionId: 'session-1',
    status: 'processing',
    payload: {
      message: 'Provider rate limit exceeded',
      code: 'REALTIME_PROVIDER_RATE_LIMIT',
      provider: 'pipecat',
      phase: 'provider_event',
      runtime: 'realtime_voice',
      realtimeRuntime: 'pipecat',
      errorCategory: 'rate_limit',
      eventType: 'error',
      sourceCode: 'rate_limit_exceeded',
      retryable: true,
      fatal: false,
      trainingSessionId: 'session-1',
      roomId: 42,
      metadata: { requestId: 'req-rate-limit' },
    },
  }))

  assert.equal(event.type, 'error')
  assert.equal(event.message, 'Provider rate limit exceeded')
  assert.equal(event.code, 'REALTIME_PROVIDER_RATE_LIMIT')
  assert.equal(event.provider, 'pipecat')
  assert.equal(event.phase, 'provider_event')
  assert.equal(event.errorCategory, 'rate_limit')
  assert.equal(event.sourceCode, 'rate_limit_exceeded')
  assert.equal(event.retryable, true)
  assert.equal(event.fatal, false)
  assert.equal(event.status, 'processing')
  assert.deepEqual(event.payload, {
    message: 'Provider rate limit exceeded',
    code: 'REALTIME_PROVIDER_RATE_LIMIT',
    provider: 'pipecat',
    phase: 'provider_event',
    runtime: 'realtime_voice',
    realtimeRuntime: 'pipecat',
    errorCategory: 'rate_limit',
    eventType: 'error',
    sourceCode: 'rate_limit_exceeded',
    retryable: true,
    fatal: false,
    trainingSessionId: 'session-1',
    roomId: 42,
    metadata: { requestId: 'req-rate-limit' },
  })
})

test('RealtimeSession decodes nested base64 audio.output events from the websocket', () => {
  let socket
  const events = []
  const statuses = []
  const client = realtimeSession.createRealtimeSession({
    url: 'ws://local/realtime',
    socketFactory: () => {
      socket = new FakeWebSocket('ws://local/realtime')
      return socket
    },
    onStatusChange: (status) => statuses.push(status),
    onEvent: (event) => events.push(event),
  })

  client.connect()
  socket.open()
  socket.onmessage?.({
    data: JSON.stringify({
      type: 'audio.output',
      sessionId: 'session-1',
      status: 'speaking',
      payload: {
        audio: Buffer.from([16, 32, 48]).toString('base64'),
        mimeType: 'audio/pcm',
        sequence: 7,
        contextId: 'tts-context-1',
        sampleRate: 24000,
        channels: 1,
        bytes: 3,
      },
    }),
  })

  assert.equal(statuses.at(-1), 'speaking')
  assert.equal(events[0].type, 'audio.output')
  assert.equal(events[0].mimeType, 'audio/pcm')
  assert.equal(events[0].sequence, 7)
  assert.equal(events[0].contextId, 'tts-context-1')
  assert.equal(events[0].sampleRate, 24000)
  assert.equal(events[0].channels, 1)
  assert.deepEqual(Array.from(new Uint8Array(events[0].audio)), [16, 32, 48])
  assert.deepEqual(Array.from(new Uint8Array(events[0].payload.audio)), [16, 32, 48])
})

test('decodeRealtimeServerEvent accepts top-level pipecat audio.output fields', () => {
  const event = realtimeSession.decodeRealtimeServerEvent(JSON.stringify({
    type: 'audio.output',
    audio: Buffer.from([1, 2]).toString('base64'),
    mimeType: 'audio/l16',
    sequence: '2',
    contextId: 'ctx-top-level',
  }))

  assert.equal(event.type, 'audio.output')
  assert.equal(event.mimeType, 'audio/l16')
  assert.equal(event.sequence, 2)
  assert.equal(event.contextId, 'ctx-top-level')
  assert.deepEqual(Array.from(new Uint8Array(event.audio)), [1, 2])
})

test('RealtimeAudioOutputQueue plays same-context chunks in sequence order', async () => {
  const played = []
  const queue = new realtimeSession.RealtimeAudioOutputQueue({
    flushDelayMs: 0,
    play: async (event) => {
      played.push(event.sequence)
    },
  })

  queue.enqueue({
    type: 'audio.output',
    audio: new Uint8Array([2]).buffer,
    sequence: 2,
    contextId: 'tts-context-1',
  })
  queue.enqueue({
    type: 'audio.output',
    audio: new Uint8Array([1]).buffer,
    sequence: 1,
    contextId: 'tts-context-1',
  })

  await new Promise((resolve) => setTimeout(resolve, 20))

  assert.deepEqual(played, [1, 2])
})

test('RealtimeAudioOutputQueue reports playback failures and drains later chunks', async () => {
  const played = []
  const errors = []
  const queue = new realtimeSession.RealtimeAudioOutputQueue({
    flushDelayMs: 0,
    play: async (event) => {
      if (event.sequence === 1) throw new Error('cannot play chunk')
      played.push(event.sequence)
    },
    onError: (error, event) => {
      errors.push({
        message: error instanceof Error ? error.message : String(error),
        sequence: event.sequence,
      })
    },
  })

  queue.enqueue({
    type: 'audio.output',
    audio: new Uint8Array([1]).buffer,
    sequence: 1,
    contextId: 'tts-context-1',
  })
  queue.enqueue({
    type: 'audio.output',
    audio: new Uint8Array([2]).buffer,
    sequence: 2,
    contextId: 'tts-context-1',
  })

  await new Promise((resolve) => setTimeout(resolve, 20))

  assert.deepEqual(errors, [{ message: 'cannot play chunk', sequence: 1 }])
  assert.deepEqual(played, [2])
})
