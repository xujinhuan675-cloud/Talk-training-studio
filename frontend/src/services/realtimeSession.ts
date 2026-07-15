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

export type RealtimeClientEvent =
  | { type: 'session.start'; sessionId?: string; metadata?: Record<string, unknown> }
  | { type: 'session.configure'; sessionId?: string; roomId?: number | string }
  | { type: 'audio.input'; audio: ArrayBuffer | Blob; mimeType?: string; sequence?: number }
  | { type: 'audio.commit' }
  | { type: 'transcript.done'; text: string; metadata?: Record<string, unknown> }
  | { type: 'conversation.item.input_audio_transcription.completed'; transcript: string; metadata?: Record<string, unknown> }
  | { type: 'input_audio_transcription.completed'; transcript: string; metadata?: Record<string, unknown> }
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
  | { type: 'audio.output'; audio: ArrayBuffer; mimeType?: string; sequence?: number }
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

export interface PersistRealtimeTranscriptMessage {
  role: RealtimeTranscriptRole
  content: string
  event_id?: string
  item_id?: string
  response_id?: string
  sender_id?: string
  metadata?: Record<string, unknown>
}

export interface PersistRealtimeTranscriptsResult {
  messages: Array<{
    id: number
    room_id: number
    sender_type: string
    sender_id: string
    content: string
    metadata?: Record<string, unknown>
  }>
}

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

function decodeServerEvent(data: unknown): RealtimeServerEvent | null {
  if (typeof data === 'string') {
    try {
      return JSON.parse(data) as RealtimeServerEvent
    } catch {
      return { type: 'transcript.delta', text: data }
    }
  }

  if (data instanceof ArrayBuffer) {
    return { type: 'audio.output', audio: data }
  }

  if (data instanceof Blob) {
    return null
  }

  return null
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
      const event = decodeServerEvent(message.data)
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
  provider,
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
  if (provider !== undefined && provider !== null && String(provider).trim()) {
    params.set('provider', String(provider).trim())
  }
  if (audioFormat !== undefined && audioFormat !== null && String(audioFormat).trim()) {
    params.set('audio_format', String(audioFormat).trim())
  }
  const query = params.toString()
  return `${base}/api/v1/training-studio/realtime${query ? `?${query}` : ''}`
}

function buildTrainingRealtimeQuery({
  sessionId,
  roomId,
}: {
  sessionId?: string | number | null
  roomId?: string | number | null
} = {}): string {
  const params = new URLSearchParams()
  if (sessionId !== undefined && sessionId !== null && String(sessionId).trim()) {
    params.set('session_id', String(sessionId).trim())
  }
  if (roomId !== undefined && roomId !== null && String(roomId).trim()) {
    params.set('room_id', String(roomId).trim())
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function getTrainingRealtimeSdpPath({
  sessionId,
  roomId,
}: {
  sessionId?: string | number | null
  roomId?: string | number | null
} = {}): string {
  return `/api/v1/training-studio/realtime/sdp${buildTrainingRealtimeQuery({ sessionId, roomId })}`
}

export async function createTrainingRealtimeSdpAnswer({
  offerSdp,
  sessionId,
  roomId,
}: {
  offerSdp: string
  sessionId?: string | number | null
  roomId?: string | number | null
}): Promise<string> {
  const response = await fetch(getTrainingRealtimeSdpPath({ sessionId, roomId }), {
    method: 'POST',
    headers: { 'Content-Type': 'application/sdp' },
    body: offerSdp,
  })
  if (!response.ok) {
    const message = await response.text().catch(() => '')
    throw new Error(message || `Realtime SDP request failed (${response.status})`)
  }
  return response.text()
}

export async function persistTrainingRealtimeTranscripts({
  sessionId,
  roomId,
  messages,
}: {
  sessionId: string | number
  roomId: string | number
  messages: PersistRealtimeTranscriptMessage[]
}): Promise<PersistRealtimeTranscriptsResult> {
  const response = await fetch('/api/v1/training-studio/realtime/transcripts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: String(sessionId),
      room_id: Number(roomId),
      messages,
    }),
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(body?.detail || body?.message || `Realtime transcript persistence failed (${response.status})`)
  }
  return body.data as PersistRealtimeTranscriptsResult
}
