export type RealtimeSessionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'preparing'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'closed'
  | 'error'

export interface RealtimeAudioOutputPayload {
  audio: ArrayBuffer
  mimeType?: string
  sequence?: number
  contextId?: string
  sampleRate?: number
  channels?: number
  bytes?: number
  encoding?: string
}

export interface RealtimeAudioOutputEvent {
  type: 'audio.output'
  audio: ArrayBuffer
  mimeType?: string
  sequence?: number
  contextId?: string
  sampleRate?: number
  channels?: number
  payload?: RealtimeAudioOutputPayload
  sessionId?: string
  status?: RealtimeSessionStatus
  createdAt?: string
}

export type RealtimeClientEvent =
  | { type: 'session.start'; sessionId?: string; metadata?: Record<string, unknown> }
  | { type: 'session.configure'; sessionId?: string; roomId?: number | string }
  | { type: 'audio.input'; audio: ArrayBuffer | Blob; mimeType?: string; sequence?: number }
  | { type: 'audio.commit' }
  | { type: 'response.cancel' }
  | { type: 'session.close'; reason?: string }

export type RealtimeServerEvent =
  | {
      type: 'session.started' | 'status.changed' | 'session.closed'
      sessionId: string
      status: RealtimeSessionStatus
      payload?: Record<string, unknown>
      createdAt?: string
    }
  | {
      type: 'session.configured'
      sessionId: string
      status: RealtimeSessionStatus
      payload: { bound: boolean; trainingSessionId?: string; roomId?: number }
      createdAt?: string
    }
  | {
      type: 'transcript.persisted'
      sessionId: string
      status: RealtimeSessionStatus
      payload: {
        trainingSessionId: string
        roomId: number
        message: {
          id: number
          room_id: number
          content: string
          sender_type: string
          sender_id: string
          metadata?: Record<string, unknown>
        }
      }
      createdAt?: string
    }
  | {
      type: 'transcript.ignored'
      sessionId: string
      status: RealtimeSessionStatus
      payload: { reason: string }
      createdAt?: string
    }
  | { type: 'session.ready'; sessionId: string }
  | RealtimeAudioOutputEvent
  | { type: 'transcript.delta'; text: string }
  | { type: 'transcript.done'; text: string }
  | { type: 'status'; status: RealtimeSessionStatus }
  | { type: 'error'; message: string; code?: string }

export interface RealtimeSessionHandlers {
  onStatusChange?: (status: RealtimeSessionStatus) => void
  onEvent?: (event: RealtimeServerEvent) => void
  onError?: (error: Error) => void
}

export interface RealtimeSessionOptions extends RealtimeSessionHandlers {
  url: string
  protocols?: string | string[]
  socketFactory?: (url: string, protocols?: string | string[]) => WebSocket
}

export type RealtimeTranscriptRole = 'user' | 'assistant'

function isRealtimeSessionStatus(value: unknown): value is RealtimeSessionStatus {
  return (
    value === 'idle'
    || value === 'connecting'
    || value === 'connected'
    || value === 'preparing'
    || value === 'listening'
    || value === 'processing'
    || value === 'speaking'
    || value === 'closed'
    || value === 'error'
  )
}

function encodeClientEvent(event: RealtimeClientEvent): string | Blob | ArrayBuffer {
  if (event.type === 'audio.input') {
    return event.audio
  }
  return JSON.stringify(event)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function optionalText(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed || undefined
}

function optionalNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string' || !value.trim()) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function wireValue(
  event: Record<string, unknown>,
  payload: Record<string, unknown> | null,
  keys: string[],
): unknown {
  for (const key of keys) {
    if (payload && payload[key] !== undefined) return payload[key]
  }
  for (const key of keys) {
    if (event[key] !== undefined) return event[key]
  }
  return undefined
}

function audioBufferFromView(value: ArrayBufferView): ArrayBuffer {
  return value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer
}

function decodeBase64Audio(value: unknown): ArrayBuffer | null {
  if (value instanceof ArrayBuffer) return value
  if (ArrayBuffer.isView(value)) return audioBufferFromView(value)
  if (typeof value !== 'string') return null

  const commaIndex = value.indexOf(',')
  const base64 = (commaIndex >= 0 ? value.slice(commaIndex + 1) : value).replace(/\s/g, '')
  const decoder = globalThis.atob
  if (typeof decoder !== 'function') return null

  try {
    const binary = decoder(base64)
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index)
    }
    return bytes.buffer
  } catch {
    return null
  }
}

function invalidAudioOutputEvent(message: string): RealtimeServerEvent {
  return { type: 'error', message, code: 'INVALID_AUDIO_OUTPUT' }
}

function normalizeAudioOutputEvent(event: Record<string, unknown>): RealtimeServerEvent {
  const payload = isRecord(event.payload) ? event.payload : null
  const audio = decodeBase64Audio(wireValue(event, payload, ['audio', 'audioData', 'data', 'chunk', 'base64']))
  if (!audio) {
    return invalidAudioOutputEvent('Realtime audio output payload is missing valid base64 audio')
  }

  const mimeType = optionalText(wireValue(event, payload, ['mimeType', 'mime_type', 'contentType', 'content_type']))
  const sequence = optionalNumber(wireValue(event, payload, ['sequence']))
  const contextId = optionalText(wireValue(event, payload, ['contextId', 'context_id']))
  const sampleRate = optionalNumber(wireValue(event, payload, ['sampleRate', 'sample_rate']))
  const channels = optionalNumber(wireValue(event, payload, ['channels']))
  const bytes = optionalNumber(wireValue(event, payload, ['bytes']))
  const encoding = optionalText(wireValue(event, payload, ['encoding']))
  const outputPayload: RealtimeAudioOutputPayload = { audio }
  if (mimeType) outputPayload.mimeType = mimeType
  if (sequence !== undefined) outputPayload.sequence = sequence
  if (contextId) outputPayload.contextId = contextId
  if (sampleRate !== undefined) outputPayload.sampleRate = sampleRate
  if (channels !== undefined) outputPayload.channels = channels
  if (bytes !== undefined) outputPayload.bytes = bytes
  if (encoding) outputPayload.encoding = encoding

  const output: RealtimeAudioOutputEvent = {
    type: 'audio.output',
    audio,
    payload: outputPayload,
  }
  if (mimeType) output.mimeType = mimeType
  if (sequence !== undefined) output.sequence = sequence
  if (contextId) output.contextId = contextId
  if (sampleRate !== undefined) output.sampleRate = sampleRate
  if (channels !== undefined) output.channels = channels
  if (typeof event.sessionId === 'string') output.sessionId = event.sessionId
  if (isRealtimeSessionStatus(event.status)) output.status = event.status
  if (typeof event.createdAt === 'string') output.createdAt = event.createdAt
  return output
}

export function decodeRealtimeServerEvent(data: unknown): RealtimeServerEvent | null {
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data)
      if (isRecord(parsed) && parsed.type === 'audio.output') {
        return normalizeAudioOutputEvent(parsed)
      }
      return parsed as RealtimeServerEvent
    } catch {
      return { type: 'transcript.delta', text: data }
    }
  }

  if (data instanceof ArrayBuffer) {
    return { type: 'audio.output', audio: data, payload: { audio: data } }
  }

  if (data instanceof Blob) {
    return null
  }

  return null
}

export type RealtimeAudioOutputPlayer = (event: RealtimeAudioOutputEvent) => Promise<void> | void

export interface RealtimeAudioOutputQueueOptions {
  play: RealtimeAudioOutputPlayer
  onError?: (error: unknown, event: RealtimeAudioOutputEvent) => void
  flushDelayMs?: number
}

type QueuedAudioOutput = {
  event: RealtimeAudioOutputEvent
  order: number
}

function compareQueuedAudioOutput(left: QueuedAudioOutput, right: QueuedAudioOutput): number {
  const leftContext = left.event.contextId || ''
  const rightContext = right.event.contextId || ''
  if (
    leftContext === rightContext
    && left.event.sequence !== undefined
    && right.event.sequence !== undefined
    && left.event.sequence !== right.event.sequence
  ) {
    return left.event.sequence - right.event.sequence
  }
  return left.order - right.order
}

export class RealtimeAudioOutputQueue {
  private readonly options: RealtimeAudioOutputQueueOptions
  private readonly flushDelayMs: number
  private pending: QueuedAudioOutput[] = []
  private playing = false
  private drainTimer: ReturnType<typeof setTimeout> | null = null
  private nextOrder = 0

  constructor(options: RealtimeAudioOutputQueueOptions) {
    this.options = options
    this.flushDelayMs = options.flushDelayMs ?? 8
  }

  get size(): number {
    return this.pending.length
  }

  enqueue(event: RealtimeAudioOutputEvent): void {
    if (event.audio.byteLength === 0) return
    this.pending.push({ event, order: this.nextOrder })
    this.nextOrder += 1
    this.scheduleDrain()
  }

  clear(): void {
    this.pending = []
    if (this.drainTimer !== null) {
      clearTimeout(this.drainTimer)
      this.drainTimer = null
    }
  }

  private scheduleDrain(): void {
    if (this.playing || this.drainTimer !== null) return
    this.drainTimer = setTimeout(() => {
      this.drainTimer = null
      void this.drain()
    }, this.flushDelayMs)
  }

  private takeNext(): QueuedAudioOutput | null {
    if (this.pending.length === 0) return null
    let nextIndex = 0
    for (let index = 1; index < this.pending.length; index += 1) {
      if (compareQueuedAudioOutput(this.pending[index], this.pending[nextIndex]) < 0) {
        nextIndex = index
      }
    }
    const [next] = this.pending.splice(nextIndex, 1)
    return next || null
  }

  private async drain(): Promise<void> {
    if (this.playing) return
    this.playing = true
    try {
      let next = this.takeNext()
      while (next) {
        try {
          await this.options.play(next.event)
        } catch (error) {
          this.options.onError?.(error, next.event)
        }
        next = this.takeNext()
      }
    } finally {
      this.playing = false
      if (this.pending.length > 0) this.scheduleDrain()
    }
  }
}

export class RealtimeSession {
  private socket: WebSocket | null = null
  private status: RealtimeSessionStatus = 'idle'
  private readonly options: RealtimeSessionOptions

  constructor(options: RealtimeSessionOptions) {
    this.options = options
  }

  get currentStatus(): RealtimeSessionStatus {
    return this.status
  }

  get isConnected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN
  }

  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return

    this.setStatus('connecting')
    const socketFactory = this.options.socketFactory || ((url, protocols) => new WebSocket(url, protocols))
    const socket = socketFactory(this.options.url, this.options.protocols)
    socket.binaryType = 'arraybuffer'
    this.socket = socket

    socket.onopen = () => {
      this.setStatus('connected')
    }

    socket.onmessage = (message) => {
      const event = decodeRealtimeServerEvent(message.data)
      if (!event) return
      if ('status' in event && isRealtimeSessionStatus(event.status)) {
        this.setStatus(event.status)
      }
      if (event.type === 'error') this.setStatus('error')
      this.options.onEvent?.(event)
    }

    socket.onerror = () => {
      const error = new Error('Realtime session WebSocket error')
      this.setStatus('error')
      this.options.onError?.(error)
    }

    socket.onclose = () => {
      this.socket = null
      this.setStatus(this.status === 'error' ? 'error' : 'closed')
    }
  }

  send(event: RealtimeClientEvent): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Realtime session is not connected')
    }
    this.socket.send(encodeClientEvent(event))
  }

  close(reason?: string): void {
    if (!this.socket) {
      this.setStatus('closed')
      return
    }
    if (this.socket.readyState === WebSocket.OPEN) {
      this.send({ type: 'session.close', reason })
    }
    this.socket.close()
  }

  private setStatus(status: RealtimeSessionStatus): void {
    this.status = status
    this.options.onStatusChange?.(status)
  }
}

export function createRealtimeSession(options: RealtimeSessionOptions): RealtimeSession {
  return new RealtimeSession(options)
}

export function getTrainingRealtimeWebSocketUrl({
  sessionId,
  roomId,
  audioFormat,
}: {
  sessionId?: string | number | null
  roomId?: string | number | null
  provider?: string | null
  audioFormat?: string | null
} = {}): string {
  const base = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
  const params = new URLSearchParams()
  if (sessionId !== undefined && sessionId !== null && String(sessionId).trim()) {
    params.set('session_id', String(sessionId).trim())
  }
  if (roomId !== undefined && roomId !== null && String(roomId).trim()) {
    params.set('room_id', String(roomId).trim())
  }
  params.set('provider', 'pipecat')
  if (audioFormat !== undefined && audioFormat !== null && String(audioFormat).trim()) {
    params.set('audio_format', String(audioFormat).trim())
  }
  const query = params.toString()
  return `${base}/api/v1/training-studio/realtime${query ? `?${query}` : ''}`
}
