export type TrainingMode = 'text' | 'voice' | 'video' | 'realtime'

export type TrainingSessionStatus = 'created' | 'active' | 'completed' | 'failed'

export interface TrainingTaskConfigDTO {
  role: string
  level: string
  tech_stack: string[]
  question_type_ratios: Record<string, number>
  question_count: number
  framework: string
  difficulty: string
  category: string
  rubric_version?: string
  rubric_weights?: Record<string, number>
}

export interface TrainingSessionDTO {
  session_id: string
  task_config: TrainingTaskConfigDTO
  mode: TrainingMode
  status: TrainingSessionStatus
  room_id?: string | null
  report_id?: string | number | null
  score_id?: string | number | null
  started_at?: string | null
  completed_at?: string | null
  message_count: number
  failure_reason?: string | null
}

export interface CreateTrainingSessionRequest {
  task_config: TrainingTaskConfigDTO
  mode: TrainingMode
}

export interface StartTrainingSessionRequest {
  room_id?: number | string
  persona_ids?: string[]
  room_name?: string
  room_type?: 'private' | 'group' | 'battle_prep' | 'defense'
  scenario_id?: number | null
}

export interface CompleteTrainingSessionRequest {
  report_id?: number | string | null
  score_id?: number | string | null
  generate_report?: boolean
}

export interface TrainingSessionReportDTO {
  id: string | number
  room_id: number
  summary: string
  content: Record<string, unknown>
  created_at?: string | null
}

export interface TranscriptTurnDTO {
  speaker: string
  text: string
  turn_id?: string
  metadata?: Record<string, unknown>
}

export interface GuideEventDTO {
  event_type: string
  severity: string
  title: string
  message: string
  suggested_text?: string
  metadata?: Record<string, unknown>
  created_at?: string
}

export interface TrainingGuidanceRequest {
  task_goal?: string
  rubric?: Record<string, unknown>
  recent_turns?: TranscriptTurnDTO[]
  message_limit?: number
}

export interface TrainingGuidanceResponse {
  session_id: string
  events: GuideEventDTO[]
  source?: string
  window_size?: number
  total_turn_count?: number
}

export interface TrainingGuidanceStreamOptions {
  message_limit?: number
  poll_interval_ms?: number
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const TRAINING_SESSION_API_BASE = '/api/v1/training-studio/sessions'

type TrainingSessionId = string | number

function sessionUrl(sessionId: TrainingSessionId, suffix = ''): string {
  return `${TRAINING_SESSION_API_BASE}/${encodeURIComponent(String(sessionId))}${suffix}`
}

async function readError(resp: Response, fallback: string): Promise<Error> {
  const json = await resp.json().catch(() => null)
  const detail = typeof json?.detail === 'string' ? json.detail : json?.detail?.message
  return new Error(json?.error?.details || detail || json?.message || fallback)
}

async function requestJson<T>(url: string, init?: RequestInit, errorMessage = 'Training session request failed'): Promise<T> {
  const resp = await fetch(url, init)
  if (!resp.ok) {
    throw await readError(resp, `${errorMessage}: ${resp.status}`)
  }
  const json: ApiResponse<T> = await resp.json()
  return json.data
}

function jsonRequest(method: 'POST' | 'PUT' | 'PATCH', body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  }
}

export async function createTrainingSession(
  data: CreateTrainingSessionRequest,
): Promise<TrainingSessionDTO> {
  return requestJson<TrainingSessionDTO>(
    TRAINING_SESSION_API_BASE,
    jsonRequest('POST', data),
    'Failed to create training session',
  )
}

export async function startTrainingSession(
  sessionId: TrainingSessionId,
  data: StartTrainingSessionRequest = {},
): Promise<TrainingSessionDTO> {
  return requestJson<TrainingSessionDTO>(
    sessionUrl(sessionId, '/start'),
    jsonRequest('POST', data),
    'Failed to start training session',
  )
}

export async function completeTrainingSession(
  sessionId: TrainingSessionId,
  data: CompleteTrainingSessionRequest = {},
): Promise<TrainingSessionDTO> {
  return requestJson<TrainingSessionDTO>(
    sessionUrl(sessionId, '/complete'),
    jsonRequest('POST', data),
    'Failed to complete training session',
  )
}

export async function getTrainingSession(sessionId: TrainingSessionId): Promise<TrainingSessionDTO> {
  return requestJson<TrainingSessionDTO>(
    sessionUrl(sessionId),
    undefined,
    'Failed to fetch training session',
  )
}

export async function getTrainingSessionReport(
  sessionId: TrainingSessionId,
): Promise<TrainingSessionReportDTO> {
  return requestJson<TrainingSessionReportDTO>(
    sessionUrl(sessionId, '/report'),
    undefined,
    'Failed to fetch training session report',
  )
}

export async function requestTrainingGuidance(
  sessionId: TrainingSessionId,
  data: TrainingGuidanceRequest = {},
): Promise<TrainingGuidanceResponse> {
  return requestJson<TrainingGuidanceResponse>(
    sessionUrl(sessionId, '/guidance'),
    jsonRequest('POST', data),
    'Failed to request training guidance',
  )
}

export function getTrainingGuidanceStreamUrl(
  sessionId: TrainingSessionId,
  options: TrainingGuidanceStreamOptions = {},
): string {
  const params = new URLSearchParams()
  if (options.message_limit !== undefined) {
    params.set('message_limit', String(options.message_limit))
  }
  if (options.poll_interval_ms !== undefined) {
    params.set('poll_interval_ms', String(options.poll_interval_ms))
  }
  const query = params.toString()
  return `${sessionUrl(sessionId, '/guidance/stream')}${query ? `?${query}` : ''}`
}

export async function listTrainingSessions(): Promise<TrainingSessionDTO[]> {
  return requestJson<TrainingSessionDTO[]>(
    TRAINING_SESSION_API_BASE,
    undefined,
    'Failed to list training sessions',
  )
}
