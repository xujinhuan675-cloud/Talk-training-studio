import type { InteractionMode, TrainingMode } from './trainingMode'
import type { ConversationTreeMessage } from './trainingConversation'
import { getAuthRequestHeaders } from './auth'
import { getErrorMessage } from '../utils/errors'

export type { TrainingMode } from './trainingMode'

export type TrainingSessionStatus = 'created' | 'active' | 'completed' | 'failed'
export const TRAINING_SESSION_MESSAGE_TREE_RUNTIME = 'conversation_message_tree' as const
export type TrainingSessionStartRuntime = typeof TRAINING_SESSION_MESSAGE_TREE_RUNTIME

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

export interface TrainingRuntimePersonaRequest {
  name: string
  role: string
  style: string
  scenario_context: string
  training_points: string[]
  difficulty?: 'easy' | 'normal' | 'hard'
}

export interface TrainingOpeningMessageRequest {
  content: string
  sender_id?: string
  metadata?: Record<string, unknown>
}

export interface StartTrainingSessionRequest {
  room_id?: number | string
  persona_ids?: string[]
  room_name?: string
  room_type?: 'private' | 'group' | 'battle_prep' | 'defense'
  scenario_id?: number | null
  runtime?: TrainingSessionStartRuntime
  runtime_persona?: TrainingRuntimePersonaRequest
  opening_message?: TrainingOpeningMessageRequest
}

export interface BuildTrainingSessionStartRequestOptions {
  useMessageTreeRuntime?: boolean
}

export interface CompleteTrainingSessionRequest {
  report_id?: number | string | null
  score_id?: number | string | null
  generate_report?: boolean
  metadata?: Record<string, unknown>
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
  pathTextState: 'with_text' | 'id_only' | 'reference_only'
  selectedPath: TrainingConversationBranchPathItem[]
  source: 'session' | 'report' | 'progress'
  sourceDetail?: string
}

export interface TrainingConversationBranchInfoSources {
  session?: TrainingSessionDTO | null
  report?: TrainingSessionReportDTO | null
  progress?: unknown
}

export interface TrainingConversationBranchSelectionInput {
  provider?: string | null
  conversationId?: string | number | null
  selectedMessageId?: string | number | null
  branchId?: string | number | null
  sourceMessageId?: string | number | null
  path?: Array<ConversationTreeMessage | TrainingConversationBranchPathItem> | null
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

export interface TrainingGuidanceStreamHandlers {
  onSnapshot: (data: TrainingGuidanceResponse) => void
  onGuidanceError: (data: unknown) => void
}

export interface TrainingMaterialAssetSummaryDTO {
  id: number
  key: string
  name: string
  content_type?: string | null
  metadata_excerpt?: Record<string, unknown>
  content_excerpt?: string | null
  content_excerpt_truncated?: boolean
}

export interface TrainingMaterialAssetListDTO {
  items: TrainingMaterialAssetSummaryDTO[]
  total: number
  skip: number
  limit: number
}

export interface MaterialReviewPointDTO {
  material_id: number
  material_title: string
  point: string
  evidence?: string | null
}

export interface MaterialReviewSourceStateDTO {
  strategy: string
  llm_used: boolean
  report_used: boolean
  replay_used: boolean
  material_snippet_used: boolean
  selected_material_ids: number[]
}

export interface MaterialReviewLimitsDTO {
  max_materials: number
  max_replay_turns: number
  material_count: number
  requested_material_count: number
  material_selection_truncated: boolean
  material_snippets_truncated: boolean
  report_context_truncated: boolean
  replay_transcript_truncated: boolean
}

export interface MaterialReviewDTO {
  session_id: string
  matched_points: MaterialReviewPointDTO[]
  missed_points: MaterialReviewPointDTO[]
  suggested_rewrites: string[]
  referenced_materials: TrainingMaterialAssetSummaryDTO[]
  source_state: MaterialReviewSourceStateDTO
  limits: MaterialReviewLimitsDTO
}

export interface ListTrainingMaterialToolConsumerOptions {
  skip?: number
  limit?: number
  includeContentExcerpt?: boolean
}

export interface ReviewAssistantMaterialReviewRequest {
  sessionId: TrainingSessionId
  materialIds?: number[]
  selectedMaterialIds?: number[]
}

export type ReviewAssistantMaterialReviewLoadState = 'idle' | 'loading' | 'ready' | 'error'
export type ReviewAssistantMaterialReviewDisplayState = 'loading' | 'error' | 'empty' | 'result'

export interface ReviewAssistantMaterialReviewDisplayInput {
  materialsState: ReviewAssistantMaterialReviewLoadState
  materialsCount: number
  materialReviewState: ReviewAssistantMaterialReviewLoadState
  materialReview?: MaterialReviewDTO | null
  materialReviewError?: string | null
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const TRAINING_SESSION_API_BASE = '/api/v1/training-studio/sessions'
const TRAINING_MATERIAL_TOOL_CONSUMER_API = '/api/v1/training-studio/tool-consumers/training-materials'
const REVIEW_ASSISTANT_MATERIAL_REVIEW_API = '/api/v1/training-studio/tool-consumers/review-assistant/material-review'

type TrainingSessionId = string | number

type BranchInfoSource = TrainingConversationBranchInfo['source']

interface BranchMetadataCandidate {
  source: BranchInfoSource
  sourceDetail: string
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

function trainingMaterialToolConsumerUrl(
  options: ListTrainingMaterialToolConsumerOptions = {},
): string {
  const params = new URLSearchParams()
  if (options.skip !== undefined) params.set('skip', String(options.skip))
  if (options.limit !== undefined) params.set('limit', String(options.limit))
  if (options.includeContentExcerpt) params.set('include_content_excerpt', 'true')
  const query = params.toString()
  return `${TRAINING_MATERIAL_TOOL_CONSUMER_API}${query ? `?${query}` : ''}`
}

function reviewAssistantMaterialReviewBody(
  data: ReviewAssistantMaterialReviewRequest,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    session_id: String(data.sessionId),
  }
  if (data.materialIds !== undefined) {
    body.material_ids = data.materialIds
  }
  if (data.selectedMaterialIds !== undefined) {
    body.selected_material_ids = data.selectedMaterialIds
  }
  return body
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

export function buildTrainingSessionStartRequest(
  data: StartTrainingSessionRequest,
  trainingMode: TrainingMode,
  interactionMode: InteractionMode,
  options: BuildTrainingSessionStartRequestOptions = {},
): StartTrainingSessionRequest {
  const request: StartTrainingSessionRequest = { ...data }
  const canUseMessageTreeRuntime = trainingMode === 'text' && interactionMode === 'turn_based'
  const useMessageTreeRuntime = canUseMessageTreeRuntime && (options.useMessageTreeRuntime ?? true)
  if (useMessageTreeRuntime) {
    request.runtime = TRAINING_SESSION_MESSAGE_TREE_RUNTIME
    delete request.room_id
  } else {
    delete request.runtime
  }
  return request
}

export function buildRoomBackedTrainingSessionStartRequest(
  data: StartTrainingSessionRequest,
  trainingMode: TrainingMode,
  interactionMode: InteractionMode,
): StartTrainingSessionRequest {
  return buildTrainingSessionStartRequest(data, trainingMode, interactionMode, {
    useMessageTreeRuntime: false,
  })
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
  const add = (source: BranchInfoSource, sourceDetail: string, metadata: unknown) => {
    const record = asRecord(metadata)
    if (record) candidates.push({ source, sourceDetail, metadata: record })
  }

  add('session', 'session.metadata', sources.session?.metadata)
  add('session', 'session.task_config.metadata', sources.session?.task_config?.metadata)
  add('report', 'report.metadata', sources.report?.metadata)
  add('report', 'report.content.metadata', asRecord(sources.report?.content)?.metadata)
  add('report', 'report.content', sources.report?.content)
  add('progress', 'progress.metadata', asRecord(sources.progress)?.metadata)

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

function forkPointFromPath(path: TrainingConversationBranchPathItem[]): string | undefined {
  for (let index = 1; index < path.length; index += 1) {
    const previous = path[index - 1]
    const current = path[index]
    if (!current.branchId || current.branchId === previous.branchId) continue
    return previous.publicId
  }
  return undefined
}

function optionalRecordEntry(
  record: Record<string, unknown>,
  key: string,
  value: string | number | boolean | undefined | null,
): void {
  if (value !== undefined && value !== null && value !== '') {
    record[key] = value
  }
}

export function buildTrainingCompletionBranchMetadata(
  selection?: TrainingConversationBranchSelectionInput | null,
): Record<string, unknown> | undefined {
  if (!selection) return undefined
  const selectedPath = (selection.path ?? [])
    .map(normalizeBranchPathItem)
    .filter((item): item is TrainingConversationBranchPathItem => Boolean(item))
  const lastPathItem = selectedPath[selectedPath.length - 1]
  const selectedMessageId = cleanText(selection.selectedMessageId) ?? lastPathItem?.publicId
  if (!selectedMessageId && selectedPath.length === 0) return undefined

  const branchId = cleanText(selection.branchId) ?? lastPathItem?.branchId ?? undefined
  const forkPointMessageId = forkPointFromPath(selectedPath)
  const pathSummary = compactPathSummary(selectedPath)
  const lastReplyPreview = lastReplyFromPath(selectedPath)
  const messageIds = selectedPath.map((item) => item.publicId)
  const replayContext = {
    purpose: 'training_replay_context',
    replayContextOnly: true,
    affectsScoring: false,
    affectsCompletion: false,
  }
  const messageTreeSelection: Record<string, unknown> = {
    ...replayContext,
    selectedMessageId,
    path: selectedPath,
    pathCount: selectedPath.length,
  }
  optionalRecordEntry(messageTreeSelection, 'provider', cleanText(selection.provider))
  optionalRecordEntry(messageTreeSelection, 'conversationId', cleanText(selection.conversationId))
  optionalRecordEntry(messageTreeSelection, 'branchId', branchId)
  optionalRecordEntry(messageTreeSelection, 'sourceMessageId', cleanText(selection.sourceMessageId))
  optionalRecordEntry(messageTreeSelection, 'forkPointMessageId', forkPointMessageId)
  optionalRecordEntry(messageTreeSelection, 'pathSummary', pathSummary)
  optionalRecordEntry(messageTreeSelection, 'lastReplyPreview', lastReplyPreview)

  return {
    messageTreeSelection,
    selectedPath: {
      ...replayContext,
      branchId: branchId ?? null,
      tailMessageId: selectedMessageId ?? null,
      messageIds,
    },
    currentBranchTail: {
      branchId: branchId ?? null,
      messageId: selectedMessageId ?? null,
    },
  }
}

export function getReviewAssistantMaterialReviewDisplayState(
  input: ReviewAssistantMaterialReviewDisplayInput,
): ReviewAssistantMaterialReviewDisplayState {
  if (input.materialsState === 'loading' || input.materialsState === 'idle') return 'loading'
  if (input.materialReviewError || input.materialReviewState === 'error') return 'error'
  if (input.materialsCount <= 0) return 'empty'
  if (input.materialReviewState === 'loading' || input.materialReviewState === 'idle') return 'loading'

  const review = input.materialReview
  if (!review) return 'empty'
  const hasResult = review.matched_points.length > 0
    || review.missed_points.length > 0
    || review.suggested_rewrites.length > 0
  return hasResult ? 'result' : 'empty'
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
  const hasPathText = selectedPath.some((item) => item.content.trim())
  const pathTextState = selectedPath.length === 0
    ? 'reference_only'
    : hasPathText
      ? 'with_text'
      : 'id_only'
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
    pathTextState,
    selectedPath,
    source: candidate.source,
    sourceDetail: candidate.sourceDetail,
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

export async function startTrainingGuidanceStream(
  sessionId: TrainingSessionId,
  options: TrainingGuidanceStreamOptions,
  handlers: TrainingGuidanceStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(
    getTrainingGuidanceStreamUrl(sessionId, options),
    withAuthHeaders({
      headers: { Accept: 'text/event-stream' },
      signal,
    }),
  )
  if (!resp.ok) {
    throw await readError(resp, `Failed to stream training guidance: ${resp.status}`)
  }
  if (!resp.body) {
    throw new Error('Training guidance stream has no response body')
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      buffer = drainTrainingGuidanceSseBuffer(buffer, handlers)
    }
    if (buffer.trim()) {
      drainTrainingGuidanceSseBuffer(`${buffer}\n\n`, handlers)
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // Reader may already be released if the stream was aborted.
    }
  }
}

function drainTrainingGuidanceSseBuffer(
  buffer: string,
  handlers: TrainingGuidanceStreamHandlers,
): string {
  let remaining = buffer
  let sepIdx: number
  while ((sepIdx = remaining.indexOf('\n\n')) !== -1) {
    const frame = remaining.slice(0, sepIdx)
    remaining = remaining.slice(sepIdx + 2)
    handleTrainingGuidanceSseFrame(frame, handlers)
  }
  return remaining
}

function handleTrainingGuidanceSseFrame(
  frame: string,
  handlers: TrainingGuidanceStreamHandlers,
): void {
  let eventName = 'message'
  const dataLines: string[] = []
  for (const rawLine of frame.replace(/\r/g, '').split('\n')) {
    if (rawLine.startsWith('event:')) {
      eventName = rawLine.slice(6).trim()
    } else if (rawLine.startsWith('data:')) {
      dataLines.push(rawLine.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) return

  const payload = dataLines.join('\n')
  let data: unknown
  try {
    data = JSON.parse(payload)
  } catch {
    data = payload
  }

  if (eventName === 'guidance_snapshot') {
    handlers.onSnapshot(data as TrainingGuidanceResponse)
  } else if (eventName === 'guidance_error') {
    handlers.onGuidanceError(data)
  }
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

export async function listTrainingMaterialToolConsumerMaterials(
  options: ListTrainingMaterialToolConsumerOptions = {},
): Promise<TrainingMaterialAssetListDTO> {
  return requestJson<TrainingMaterialAssetListDTO>(
    trainingMaterialToolConsumerUrl(options),
    undefined,
    'Failed to list training materials',
  )
}

export async function requestReviewAssistantMaterialReview(
  data: ReviewAssistantMaterialReviewRequest,
): Promise<MaterialReviewDTO> {
  return requestJson<MaterialReviewDTO>(
    REVIEW_ASSISTANT_MATERIAL_REVIEW_API,
    jsonRequest('POST', reviewAssistantMaterialReviewBody(data)),
    'Failed to review training materials',
  )
}
