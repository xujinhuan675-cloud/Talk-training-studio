import { getAuthRequestHeaders } from './auth'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface VoicePreferenceConfig {
  llm_provider: string
  llm_base_url: string | null
  llm_default_model: string
  llm_wire_api: string
  llm_api_key_configured: boolean
  llm_api_key_preview: string | null
  tts_provider: string
  tts_base_url: string | null
  tts_model: string
  tts_api_key_configured: boolean
  tts_api_key_preview: string | null
  stt_provider: string
  stt_base_url: string | null
  stt_model: string
  stt_api_key_configured: boolean
  stt_api_key_preview: string | null
  stt_api_key_source: 'stt' | 'tts' | 'llm' | 'missing'
  stt_use_tts_api_key: boolean
  realtime_api_key_configured: boolean
  realtime_effective_api_key_configured: boolean
  realtime_api_key_preview: string | null
  realtime_api_key_source: 'realtime' | 'llm' | 'missing'
  realtime_provider: string
  realtime_base_url: string | null
  realtime_model: string
  realtime_voice: string
  realtime_transcription_model: string | null
  updated_at: string
}

export interface VoicePreferenceUpdate {
  llm_provider?: string
  llm_base_url?: string | null
  llm_default_model?: string
  llm_wire_api?: string
  llm_api_key?: string
  clear_llm_api_key?: boolean
  tts_provider?: string
  tts_base_url?: string | null
  tts_model?: string
  tts_api_key?: string
  clear_tts_api_key?: boolean
  stt_provider?: string
  stt_base_url?: string | null
  stt_model?: string
  stt_api_key?: string
  clear_stt_api_key?: boolean
  stt_use_tts_api_key?: boolean
  realtime_api_key?: string
  clear_realtime_api_key?: boolean
  realtime_provider?: string
  realtime_base_url?: string | null
  realtime_model?: string
  realtime_voice?: string
  realtime_transcription_model?: string | null
}

const VOICE_CONFIG_API = '/api/v1/training-studio/voice-config'

function hasObjectShape(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function unwrapApiResponse<T>(value: ApiResponse<T> | T): T {
  if (hasObjectShape(value) && 'data' in value) {
    return value.data as T
  }
  return value as T
}

async function readError(resp: Response, fallback: string): Promise<Error> {
  const json = await resp.json().catch(() => null)
  const detail = typeof json?.detail === 'string' ? json.detail : json?.detail?.message
  return new Error(json?.error?.details || detail || json?.message || `${fallback}: ${resp.status}`)
}

async function requestVoiceConfig<T>(init?: RequestInit, fallback = 'Voice config request failed'): Promise<T> {
  const resp = await fetch(VOICE_CONFIG_API, {
    ...init,
    headers: {
      ...getAuthRequestHeaders(),
      ...(init?.headers as Record<string, string> | undefined),
    },
  })
  if (!resp.ok) {
    throw await readError(resp, fallback)
  }
  return unwrapApiResponse<T>(await resp.json())
}

export async function fetchVoiceConfig(): Promise<VoicePreferenceConfig> {
  return requestVoiceConfig<VoicePreferenceConfig>(undefined, 'Failed to fetch voice config')
}

export async function saveVoiceConfig(update: VoicePreferenceUpdate): Promise<VoicePreferenceConfig> {
  return requestVoiceConfig<VoicePreferenceConfig>(
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    },
    'Failed to save voice config',
  )
}
