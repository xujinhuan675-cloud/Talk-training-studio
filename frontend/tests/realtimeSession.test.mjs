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
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `realtime-session-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
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
    'wss://demo.example/api/v1/training-studio/realtime?session_id=session+1&room_id=42&provider=openai&audio_format=pcm16',
  )
})

test('getTrainingRealtimeSdpPath builds a bound SDP proxy path', () => {
  const path = realtimeSession.getTrainingRealtimeSdpPath({
    sessionId: 'session 1',
    roomId: 42,
  })

  assert.equal(
    path,
    '/api/v1/training-studio/realtime/sdp?session_id=session+1&room_id=42',
  )
})

test('persistTrainingRealtimeTranscripts posts normalized payload', async () => {
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({ data: { messages: [] } }),
    }
  }

  await realtimeSession.persistTrainingRealtimeTranscripts({
    sessionId: 'session-1',
    roomId: 42,
    messages: [
      {
        role: 'assistant',
        content: 'That is a useful next step.',
        event_id: 'evt-1',
      },
    ],
  })

  assert.equal(calls[0].url, '/api/v1/training-studio/realtime/transcripts')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    session_id: 'session-1',
    room_id: 42,
    messages: [
      {
        role: 'assistant',
        content: 'That is a useful next step.',
        event_id: 'evt-1',
      },
    ],
  })
})

test('RealtimeSession sends final transcript events as JSON frames', () => {
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
    type: 'conversation.item.input_audio_transcription.completed',
    transcript: 'We can start with a pilot.',
  })

  assert.deepEqual(statuses, ['connecting', 'connected'])
  assert.equal(socket.url, 'ws://local/realtime')
  assert.deepEqual(JSON.parse(socket.sent[0]), {
    type: 'conversation.item.input_audio_transcription.completed',
    transcript: 'We can start with a pilot.',
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
