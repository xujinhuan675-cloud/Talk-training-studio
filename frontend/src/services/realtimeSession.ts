export type RealtimeSessionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'closed'
  | 'error'

export type RealtimeClientEvent =
  | { type: 'session.start'; sessionId?: string; metadata?: Record<string, unknown> }
  | { type: 'audio.input'; audio: ArrayBuffer | Blob; mimeType?: string; sequence?: number }
  | { type: 'audio.commit' }
  | { type: 'response.cancel' }
  | { type: 'session.close'; reason?: string }

export type RealtimeServerEvent =
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
      if (event.type === 'status') this.setStatus(event.status)
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
