import type { TrainingMode } from './trainingMode'
import type { ConversationTreeMessage } from './trainingConversation'
import { getAuthRequestHeaders } from './auth'
import { getErrorMessage } from '../utils/errors'

export type { TrainingMode } from './trainingMode'

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
  metadata?: Record<string, unknown>
}

export interface TrainingSessionDTO {
  session_id: string
  task_config: TrainingTaskConfigDTO
  mode: TrainingMode
  scenario_template_id?: string | null
  user_id?: string | null
  team_id?: string | null
  status: TrainingSessionStatus
  room_id?: string | null
  report_id?: string | number | null
  score_id?: string | number | null
  started_at?: string | null
  completed_at?: string | null
  message_count: number
  failure_reason?: string | null
  metadata?: Record<string, unknown> | null
}

export interface CreateTrainingSessionRequest {
  task_config: TrainingTaskConfigDTO
  mode: TrainingMode
  scenario_template_id?: string | null
  user_id?: string | null
  team_id?: string | null
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
  metadata?: Record<string, unknown> | null
}

export type TrainingConversationBranchPathItem = Pick<
  ConversationTreeMessage,
  'publicId' | 'role' | 'content' | 'branchId' | 'parentMessageId'
>

export interface TrainingConversationBranchInfo {
  provider?: string
  conversationId?: string
  branchId?: string
  selectedTailMessageId?: string
  forkPointMessageId?: string
  pathCount?: number
  pathSummary?: string
  lastReplyPreview?: string
  selectedPath: TrainingConversationBranchPathItem[]
  source: 'session' | 'report' | 'progress'
}

export interface TrainingConversationBranchInfoSources {
  session?: TrainingSessionDTO | null
  report?: TrainingSessionReportDTO | null
  progress?: unknown
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

export interface PersistTrainingGuidanceEventsRequest {
  events: GuideEventDTO[]
  reason?: string
  source?: string
  window_size?: number
  total_turn_count?: number
  trigger?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface PersistTrainingGuidanceEventsResponse {
  batch_id: string
  saved_count: number
  messages?: unknown[]
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

type BranchInfoSource = TrainingConversationBranchInfo['source']

interface BranchMetadataCandidate {
  source: BranchInfoSource
  metadata: Record<string, unknown>
}

export interface ListTrainingSessionsOptions {
  skip?: number
  limit?: number
  userId?: string | null
  teamId?: string | null
  scenarioTemplateId?: string | null
}

function sessionUrl(sessionId: TrainingSessionId, suffix = ''): string {
  return `${TRAINING_SESSION_API_BASE}/${encodeURIComponent(String(sessionId))}${suffix}`
}

function sessionsUrl(options: ListTrainingSessionsOptions = {}): string {
  const params = new URLSearchParams()
  if (options.skip !== undefined) params.set('skip', String(options.skip))
  if (options.limit !== undefined) params.set('limit', String(options.limit))
  if (options.userId) params.set('user_id', options.userId)
  if (options.teamId) params.set('team_id', options.teamId)
  if (options.scenarioTemplateId) params.set('scenario_template_id', options.scenarioTemplateId)
  const query = params.toString()
  return `${TRAINING_SESSION_API_BASE}${query ? `?${query}` : ''}`
}

async function readError(resp: Response, fallback: string): Promise<Error> {
  if ([502, 503, 504].includes(resp.status)) {
    return new Error(
      `${fallback}: backend service unavailable. Restart the local backend or check VITE_API_URL.`,
    )
  }
  const json = await resp.json().catch(() => null)
  return new Error(getErrorMessage(json, fallback))
}

async function requestJson<T>(url: string, init?: RequestInit, errorMessage = 'Training session request failed'): Promise<T> {
  const resp = await fetch(url, withAuthHeaders(init))
  if (!resp.ok) {
    throw await readError(resp, `${errorMessage}: ${resp.status}`)
  }
  const json: ApiResponse<T> = await resp.json()
  return json.data
}

function withAuthHeaders(init: RequestInit = {}): RequestInit {
  return {
    ...init,
    headers: {
      ...getAuthRequestHeaders(),
      ...(init.headers as Record<string, string> | undefined),
    },
  }
}

function jsonRequest(method: 'POST' | 'PUT' | 'PATCH', body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  }
}

function cleanText(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined
  if (typeof value === 'object' || typeof value === 'function' || typeof value === 'symbol') return undefined
  const text = String(value).trim()
  return text || undefined
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function firstText(record: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const text = cleanText(record[key])
    if (text) return text
  }
  return undefined
}

function firstNumber(record: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key]
    const number = typeof value === 'number' ? value : Number(cleanText(value))
    if (Number.isFinite(number) && number > 0) return Math.round(number)
  }
  return undefined
}

function firstArray(record: Record<string, unknown>, keys: string[]): unknown[] {
  for (const key of keys) {
    const value = record[key]
    if (Array.isArray(value)) return value
  }
  return []
}

function collectBranchMetadataCandidates(
  sources: TrainingConversationBranchInfoSources,
): BranchMetadataCandidate[] {
  const candidates: BranchMetadataCandidate[] = []
  const add = (source: BranchInfoSource, metadata: unknown) => {
    const record = asRecord(metadata)
    if (record) candidates.push({ source, metadata: record })
  }

  add('session', sources.session?.metadata)
  add('session', sources.session?.task_config?.metadata)
  add('report', sources.report?.metadata)
  add('report', asRecord(sources.report?.content)?.metadata)
  add('report', sources.report?.content)
  add('progress', asRecord(sources.progress)?.metadata)

  return candidates
}

const branchRecordKeys = [
  'conversation',
  'conversationRef',
  'conversation_ref',
  'messageTree',
  'message_tree',
  'messageTreeSelection',
  'message_tree_selection',
  'conversationTree',
  'conversation_tree',
  'trainingConversation',
  'training_conversation',
  'pathContext',
  'path_context',
  'branchContext',
  'branch_context',
  'replayContext',
  'replay_context',
  'selectedPath',
  'selected_path',
  'currentPath',
  'current_path',
  'currentBranchTail',
  'current_branch_tail',
  'branch',
  'message',
  'messageRef',
  'message_ref',
]

const providerKeys = ['provider', 'conversationProvider', 'conversation_provider']
const conversationIdKeys = ['conversationId', 'conversation_id']
const branchIdKeys = ['branchId', 'branch_id', 'selectedBranchId', 'selected_branch_id']
const selectedTailKeys = [
  'selectedTailMessageId',
  'selected_tail_message_id',
  'selectedMessageId',
  'selected_message_id',
  'branchTailMessageId',
  'branch_tail_message_id',
  'messagePublicId',
  'message_public_id',
  'publicId',
  'public_id',
  'tailMessageId',
  'tail_message_id',
  'tailId',
  'tail_id',
  'tailPublicId',
  'tail_public_id',
  'currentTailMessageId',
  'current_tail_message_id',
  'messageId',
  'message_id',
]
const forkPointKeys = [
  'forkPointMessageId',
  'fork_point_message_id',
  'forkedFromMessageId',
  'forked_from_message_id',
  'forkPointPublicId',
  'fork_point_public_id',
  'forkParentMessageId',
  'fork_parent_message_id',
  'branchFromMessageId',
  'branch_from_message_id',
  'splitFromMessageId',
  'split_from_message_id',
  'sourceMessageId',
  'source_message_id',
  'parentMessageId',
  'parent_message_id',
]
const lastReplyKeys = [
  'lastReply',
  'last_reply',
  'lastReplyPreview',
  'last_reply_preview',
  'lastResponse',
  'last_response',
  'lastMessage',
  'last_message',
  'lastMessageContent',
  'last_message_content',
  'replyPreview',
  'reply_preview',
  'tailPreview',
  'tail_preview',
]
const pathKeys = [
  'path',
  'selectedPath',
  'selected_path',
  'currentPath',
  'current_path',
  'messagePath',
  'message_path',
  'pathMessages',
  'path_messages',
  'selectedMessages',
  'selected_messages',
  'messageIds',
  'message_ids',
  'messagePathIds',
  'message_path_ids',
  'pathMessageIds',
  'path_message_ids',
  'selectedMessageIds',
  'selected_message_ids',
  'nodeIds',
  'node_ids',
]
const pathCountKeys = [
  'pathCount',
  'path_count',
  'selectedPathCount',
  'selected_path_count',
  'selectedPathLength',
  'selected_path_length',
]
const pathSummaryKeys = [
  'pathSummary',
  'path_summary',
  'selectedPathSummary',
  'selected_path_summary',
  'pathLabel',
  'path_label',
]

function branchRecords(metadata: Record<string, unknown>): Record<string, unknown>[] {
  const records: Record<string, unknown>[] = [metadata]

  branchRecordKeys.forEach((key) => {
    const record = asRecord(metadata[key])
    if (record) records.push(record)
  })

  return records
}

function normalizeBranchPathItem(value: unknown): TrainingConversationBranchPathItem | null {
  const text = cleanText(value)
  if (text && typeof value !== 'object') {
    return {
      publicId: text,
      role: '',
      content: '',
      branchId: null,
      parentMessageId: null,
    }
  }

  const record = asRecord(value)
  if (!record) return null
  const publicId = firstText(record, [
    'publicId',
    'public_id',
    'messagePublicId',
    'message_public_id',
    'id',
    'messageId',
    'message_id',
  ])
  if (!publicId) return null

  return {
    publicId,
    role: firstText(record, ['role', 'speaker', 'sender', 'senderType', 'sender_type']) ?? '',
    content: firstText(record, ['content', 'text', 'message', 'preview', 'title']) ?? '',
    branchId: firstText(record, branchIdKeys) ?? null,
    parentMessageId: firstText(record, forkPointKeys) ?? null,
  }
}

function normalizeBranchPath(records: Record<string, unknown>[]): TrainingConversationBranchPathItem[] {
  for (const record of records) {
    const defaultBranchId = firstText(record, branchIdKeys) ?? null
    const path = firstArray(record, pathKeys)
      .map(normalizeBranchPathItem)
      .filter((item): item is TrainingConversationBranchPathItem => Boolean(item))
      .map((item) => ({
        ...item,
        branchId: item.branchId ?? defaultBranchId,
      }))
    if (path.length > 0) return path
  }
  return []
}

function compactPathSummary(path: TrainingConversationBranchPathItem[]): string | undefined {
  const parts = path
    .slice(-3)
    .map((item) => item.content.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
  if (parts.length === 0) return undefined
  const summary = parts.join(' / ')
  return summary.length > 180 ? `${summary.slice(0, 177)}...` : summary
}

function previewText(value: unknown): string | undefined {
  const directText = cleanText(value)
  if (directText) return directText

  const record = asRecord(value)
  if (!record) return undefined
  return firstText(record, [
    'content',
    'text',
    'message',
    'preview',
    'reply',
    'response',
    'body',
    'title',
  ])
}

function firstPreview(records: Record<string, unknown>[], keys: string[]): string | undefined {
  for (const record of records) {
    for (const key of keys) {
      const text = previewText(record[key])
      if (text) return text
    }
  }
  return undefined
}

function lastReplyFromPath(path: TrainingConversationBranchPathItem[]): string | undefined {
  const items = [...path].reverse()
  const assistantReply = items.find((item) => (
    Boolean(item.content) && !['user', 'system'].includes(item.role.toLowerCase())
  ))
  return assistantReply?.content || items.find((item) => Boolean(item.content))?.content
}

function branchInfoFromCandidate(
  candidate: BranchMetadataCandidate,
): TrainingConversationBranchInfo | null {
  const records = branchRecords(candidate.metadata)
  const selectedPath = normalizeBranchPath(records)
  const lastPathItem = selectedPath[selectedPath.length - 1]
  const provider = records.map((record) => firstText(record, providerKeys)).find(Boolean)
  const conversationId = records.map((record) => firstText(record, conversationIdKeys)).find(Boolean)
  const branchId = records.map((record) => firstText(record, branchIdKeys)).find(Boolean)
    ?? lastPathItem?.branchId
    ?? undefined
  const selectedTailMessageId = records.map((record) => firstText(record, selectedTailKeys)).find(Boolean)
    ?? lastPathItem?.publicId
  const forkPointMessageId = records.map((record) => firstText(record, forkPointKeys)).find(Boolean)
    ?? lastPathItem?.parentMessageId
    ?? undefined
  const explicitPathCount = records.map((record) => firstNumber(record, pathCountKeys)).find(Boolean)
  const pathCount = selectedPath.length > 0 ? selectedPath.length : explicitPathCount
  const pathSummary = records.map((record) => firstText(record, pathSummaryKeys)).find(Boolean)
    ?? compactPathSummary(selectedPath)
  const lastReplyPreview = firstPreview(records, lastReplyKeys) ?? lastReplyFromPath(selectedPath)

  const hasPathContext = Boolean(selectedTailMessageId || forkPointMessageId || pathCount || pathSummary || lastReplyPreview)
  if (!hasPathContext && (!branchId || branchId === 'main')) return null

  return {
    provider,
    conversationId,
    branchId,
    selectedTailMessageId,
    forkPointMessageId,
    pathCount,
    pathSummary,
    lastReplyPreview,
    selectedPath,
    source: candidate.source,
  }
}

export function getTrainingConversationBranchInfo(
  sources: TrainingConversationBranchInfoSources,
): TrainingConversationBranchInfo | null {
  const candidates = collectBranchMetadataCandidates(sources)
  for (const candidate of candidates) {
    const info = branchInfoFromCandidate(candidate)
    if (info) return info
  }
  return null
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

export async function persistTrainingGuidanceEvents(
  sessionId: TrainingSessionId,
  data: PersistTrainingGuidanceEventsRequest,
): Promise<PersistTrainingGuidanceEventsResponse> {
  return requestJson<PersistTrainingGuidanceEventsResponse>(
    sessionUrl(sessionId, '/guidance-events'),
    jsonRequest('POST', data),
    'Failed to save training guidance events',
  )
}

export function getTrainingGuidanceStreamUrl(
  sessionId: TrainingSessionId,
  options: TrainingGuidanceStreamOptions = {},
): string {
  const params = new URLSearchParams()
  const mockUser = getAuthRequestHeaders()['X-Mock-User']
  if (mockUser) {
    params.set('mock_user', mockUser)
  }
  if (options.message_limit !== undefined) {
    params.set('message_limit', String(options.message_limit))
  }
  if (options.poll_interval_ms !== undefined) {
    params.set('poll_interval_ms', String(options.poll_interval_ms))
  }
  const query = params.toString()
  return `${sessionUrl(sessionId, '/guidance/stream')}${query ? `?${query}` : ''}`
}

export async function listTrainingSessions(
  options: ListTrainingSessionsOptions = {},
): Promise<TrainingSessionDTO[]> {
  return requestJson<TrainingSessionDTO[]>(
    sessionsUrl(options),
    undefined,
    'Failed to list training sessions',
  )
}
