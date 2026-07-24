import { getAuthRequestHeaders } from './auth'

export const CLIENT_REALTIME_EVENT_API = '/api/v1/training-studio/client-events'

export const CLIENT_REALTIME_EVENT_TYPES = [
  'realtime.start_requested',
  'realtime.ws_connected',
  'realtime.ws_error',
  'realtime.configure_failed',
  'realtime.start_failed',
  'realtime.server_error',
  'realtime.closed',
  'mic.unavailable',
  'mic.permission_denied',
  'mic.capture_started',
  'audio.input_send_failed',
  'audio.output_received',
  'audio.output_played',
  'audio.output_playback_failed',
  'transcript.persisted',
] as const

export type ClientRealtimeEventType = typeof CLIENT_REALTIME_EVENT_TYPES[number]
export type ClientEventSeverity = 'debug' | 'info' | 'warning' | 'error'

export interface ClientRealtimeEventInput {
  eventType: ClientRealtimeEventType
  eventCategory?: string
  severity?: ClientEventSeverity
  trainingSessionId?: string | number | null
  roomId?: string | number | null
  provider?: string | null
  realtimeProfile?: string | null
  errorCategory?: string | null
  message?: string | null
  payload?: Record<string, unknown>
}

export interface ClientEventLoggerOptions {
  fetchFn?: typeof fetch
  maxPayloadBytes?: number
}

const CLIENT_REALTIME_EVENT_TYPE_SET = new Set<string>(CLIENT_REALTIME_EVENT_TYPES)
const CLIENT_EVENT_SEVERITIES = new Set<string>(['debug', 'info', 'warning', 'error'])
const CLIENT_EVENT_PAYLOAD_STRING_MAX_CHARS = 512
const CLIENT_EVENT_PAYLOAD_ARRAY_MAX_ITEMS = 20
const CLIENT_EVENT_PAYLOAD_MAX_DEPTH = 5
const CLIENT_EVENT_PAYLOAD_MAX_BYTES = 4096

const SENSITIVE_KEY_SET = new Set<string>([
  'apikey',
  'api_key',
  'authorization',
  'authtoken',
  'auth_token',
  'bearertoken',
  'bearer_token',
  'clientsecret',
  'client_secret',
  'credential',
  'credentials',
  'openaiapikey',
  'openai_api_key',
  'password',
  'privatekey',
  'private_key',
  'secret',
  'token',
])

const OMIT_PAYLOAD_KEY_SET = new Set<string>([
  'audio',
  'audiodata',
  'blob',
  'buffer',
  'content',
  'data',
  'pcm',
  'raw',
  'samples',
  'text',
  'transcript',
  'utterance',
])

function normalizePayloadKey(key: string): { snake: string; compact: string } {
  const lowered = key.trim().toLowerCase()
  const snake = lowered.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  const compact = lowered.replace(/[^a-z0-9]+/g, '')
  return { snake, compact }
}

function shouldOmitPayloadKey(key: string): boolean {
  const { snake, compact } = normalizePayloadKey(key)
  return (
    SENSITIVE_KEY_SET.has(snake)
    || SENSITIVE_KEY_SET.has(compact)
    || OMIT_PAYLOAD_KEY_SET.has(snake)
    || OMIT_PAYLOAD_KEY_SET.has(compact)
    || snake.endsWith('_api_key')
    || snake.endsWith('_authorization')
    || snake.endsWith('_password')
    || snake.endsWith('_secret')
    || snake.endsWith('_token')
    || snake.endsWith('_audio')
    || snake.endsWith('_blob')
    || snake.endsWith('_content')
    || snake.endsWith('_raw')
    || snake.endsWith('_text')
    || snake.endsWith('_transcript')
    || compact.endsWith('apikey')
    || compact.endsWith('authorization')
    || compact.endsWith('password')
    || compact.endsWith('secret')
    || compact.endsWith('token')
    || compact.endsWith('audio')
    || compact.endsWith('blob')
    || compact.endsWith('content')
    || compact.endsWith('raw')
    || compact.endsWith('text')
    || compact.endsWith('transcript')
  )
}

export function redactClientEventText(value: string): string {
  const redacted = value
    .replace(/(\bbearer\s+)[^\s,;}\]]+/gi, '$1***')
    .replace(/\bsk-[A-Za-z0-9][A-Za-z0-9_-]{3,}\b/g, 'sk-***')
    .replace(/\b(api[_-]?key|apikey|authorization|password|secret|token)(\s*[:=]\s*)([^\s,;}\]]+)/gi, '$1$2***')

  if (redacted.length <= CLIENT_EVENT_PAYLOAD_STRING_MAX_CHARS) return redacted
  return `${redacted.slice(0, CLIENT_EVENT_PAYLOAD_STRING_MAX_CHARS)}...[truncated]`
}

function binaryDescriptor(value: unknown): Record<string, unknown> | null {
  if (typeof Blob !== 'undefined' && value instanceof Blob) {
    return { omitted: true, kind: 'blob', bytes: value.size, type: value.type || undefined }
  }
  if (value instanceof ArrayBuffer) {
    return { omitted: true, kind: 'array_buffer', bytes: value.byteLength }
  }
  if (ArrayBuffer.isView(value)) {
    return { omitted: true, kind: 'array_buffer_view', bytes: value.byteLength }
  }
  return null
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function sanitizeClientEventPayloadValue(
  value: unknown,
  depth: number,
  seen: WeakSet<object>,
): unknown {
  const binary = binaryDescriptor(value)
  if (binary) return binary
  if (typeof value === 'string') return redactClientEventText(value)
  if (typeof value === 'number' || typeof value === 'boolean') return value
  if (value === null || value === undefined) return undefined
  if (depth > CLIENT_EVENT_PAYLOAD_MAX_DEPTH) return '[max_depth_exceeded]'

  if (Array.isArray(value)) {
    if (seen.has(value)) return '[circular]'
    seen.add(value)
    const sanitized = value
      .slice(0, CLIENT_EVENT_PAYLOAD_ARRAY_MAX_ITEMS)
      .map((item) => sanitizeClientEventPayloadValue(item, depth + 1, seen))
      .filter((item) => item !== undefined)
    const omittedItems = value.length - CLIENT_EVENT_PAYLOAD_ARRAY_MAX_ITEMS
    if (omittedItems > 0) {
      sanitized.push({ truncated: true, omittedItems })
    }
    return sanitized
  }

  if (isPlainObject(value)) {
    if (seen.has(value)) return '[circular]'
    seen.add(value)
    const sanitized: Record<string, unknown> = {}
    Object.entries(value).forEach(([key, nestedValue]) => {
      if (shouldOmitPayloadKey(key)) return
      const safeValue = sanitizeClientEventPayloadValue(nestedValue, depth + 1, seen)
      if (safeValue !== undefined) {
        sanitized[key] = safeValue
      }
    })
    return sanitized
  }

  return undefined
}

export function sanitizeClientEventPayload(payload: Record<string, unknown> = {}): Record<string, unknown> {
  const sanitized = sanitizeClientEventPayloadValue(payload, 0, new WeakSet())
  return isPlainObject(sanitized) ? sanitized : {}
}

function stringByteLength(value: string): number {
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(value).length
  }
  return value.length
}

function boundedClientEventPayload(
  payload: Record<string, unknown> = {},
  maxPayloadBytes = CLIENT_EVENT_PAYLOAD_MAX_BYTES,
): Record<string, unknown> {
  const sanitized = sanitizeClientEventPayload(payload)
  const serialized = JSON.stringify(sanitized)
  const payloadBytes = stringByteLength(serialized)
  const limit = Math.max(256, maxPayloadBytes)
  if (payloadBytes <= limit) return sanitized
  return {
    truncated: true,
    payloadBytes,
    maxPayloadBytes: limit,
  }
}

function cleanOptionalText(value: string | number | null | undefined): string | undefined {
  if (value === null || value === undefined) return undefined
  const text = String(value).trim()
  return text || undefined
}

function normalizeSeverity(value: ClientEventSeverity | undefined): ClientEventSeverity {
  return CLIENT_EVENT_SEVERITIES.has(value || '') ? (value as ClientEventSeverity) : 'info'
}

export function buildRealtimeClientEventRequest(
  event: ClientRealtimeEventInput,
  options: ClientEventLoggerOptions = {},
): Record<string, unknown> | null {
  const eventType = cleanOptionalText(event.eventType)
  if (!eventType || !CLIENT_REALTIME_EVENT_TYPE_SET.has(eventType)) return null

  const body: Record<string, unknown> = {
    eventType,
    eventCategory: cleanOptionalText(event.eventCategory) || 'realtime_voice',
    severity: normalizeSeverity(event.severity),
    provider: cleanOptionalText(event.provider) || 'pipecat',
    payload: boundedClientEventPayload(event.payload, options.maxPayloadBytes),
  }
  const trainingSessionId = cleanOptionalText(event.trainingSessionId)
  const roomId = cleanOptionalText(event.roomId)
  const realtimeProfile = cleanOptionalText(event.realtimeProfile)
  const errorCategory = cleanOptionalText(event.errorCategory)
  const message = cleanOptionalText(event.message)

  if (trainingSessionId) body.trainingSessionId = trainingSessionId
  if (roomId) body.roomId = roomId
  if (realtimeProfile) body.realtimeProfile = realtimeProfile
  if (errorCategory) body.errorCategory = errorCategory
  if (message) body.message = redactClientEventText(message)

  return body
}

export async function logRealtimeClientEvent(
  event: ClientRealtimeEventInput,
  options: ClientEventLoggerOptions = {},
): Promise<boolean> {
  const body = buildRealtimeClientEventRequest(event, options)
  if (!body) return false

  const fetchFn = options.fetchFn || globalThis.fetch
  if (typeof fetchFn !== 'function') return false

  try {
    const response = await fetchFn(CLIENT_REALTIME_EVENT_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthRequestHeaders(),
      },
      body: JSON.stringify(body),
      keepalive: true,
    })
    return response.ok
  } catch {
    return false
  }
}
