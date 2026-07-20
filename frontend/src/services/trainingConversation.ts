export type TrainingRuntimeMode = 'text' | 'voice' | 'video' | 'realtime'
export type TrainingTurnRole = 'system' | 'user' | 'assistant'
export type TrainingTranscriptSpeaker = 'user' | 'counterpart' | 'system'
export type TalkWiseSender = 'user' | 'persona' | 'system'
export type TrainingRuntimeTransport =
  | 'message'
  | 'session'
  | 'realtime_websocket'

export interface ConversationRef {
  provider: string
  conversationId: string
  branchTailMessageId: string | null
  legacyRoomId: string | null
  metadata: Record<string, unknown>
}

export interface ConversationRefInput {
  provider?: string | null
  conversationId?: string | number | null
  conversation_id?: string | number | null
  branchTailMessageId?: string | number | null
  branch_tail_message_id?: string | number | null
  legacyRoomId?: string | number | null
  legacy_room_id?: string | number | null
  metadata?: Record<string, unknown> | null
}

export interface TrainingTurnInput {
  id?: string | number | null
  turnId?: string | number | null
  turn_id?: string | number | null
  messageId?: string | number | null
  message_id?: string | number | null
  role?: string | null
  speaker?: string | null
  sender?: string | null
  senderType?: string | null
  sender_type?: string | null
  senderId?: string | number | null
  sender_id?: string | number | null
  text?: string | null
  content?: string | null
  metadata?: Record<string, unknown> | null
  parentMessageId?: string | number | null
  parent_message_id?: string | number | null
  branchId?: string | number | null
  branch_id?: string | number | null
  provider?: string | null
  model?: string | null
  modelSpec?: string | null
  model_spec?: string | null
}

export interface TrainingTurn {
  turnId: string | null
  role: TrainingTurnRole
  speaker: TrainingTranscriptSpeaker
  sender: TalkWiseSender
  senderId: string | null
  text: string
  content: string
  metadata: Record<string, unknown>
  parentMessageId: string | null
  branchId: string | null
  provider: string | null
  model: string | null
  modelSpec: string | null
}

export interface ResolveRuntimeEndpointOptions {
  mode: TrainingRuntimeMode
  provider?: string | null
  conversation?: ConversationRefInput | null
  roomId?: string | number | null
  sessionId?: string | number | null
  transport?: TrainingRuntimeTransport | null
}

export interface BuildTrainingConversationPayloadInput {
  mode: TrainingRuntimeMode
  provider?: string | null
  conversation: ConversationRefInput
  turn?: TrainingTurnInput
  turns?: TrainingTurnInput[]
  metadata?: Record<string, unknown> | null
  endpoint?: string | null
  endpointTransport?: TrainingRuntimeTransport | null
  roomId?: string | number | null
  sessionId?: string | number | null
}

export interface TrainingConversationPayload {
  mode: TrainingRuntimeMode
  provider: string
  endpoint: string
  conversation: ConversationRef
  turns: TrainingTurn[]
  metadata: Record<string, unknown>
}

export type ConversationTreeActionKind =
  | 'branch'
  | 'locate'
  | 'path'
  | 'children'
  | 'fork'
  | 'edit'
  | 'retry'
  | 'search'

export interface ConversationTreeMessageActionEndpoints {
  actions: string
  locate: string
  path: string
  children: string
  fork: string
  edit: string
  retry: string
  search: string
}

export interface ConversationTreeMessageActionContextInput {
  provider?: string | null
  conversation?: ConversationRefInput | null
  conversationId?: string | number | null
  conversation_id?: string | number | null
  messagePublicId?: string | number | null
  message_public_id?: string | number | null
  branchId?: string | number | null
  branch_id?: string | number | null
  metadata?: Record<string, unknown> | null
  turn?: TrainingTurnInput | null
}

export interface ConversationTreeMessageActionContext {
  provider: string
  conversationId: string
  messagePublicId: string
  branchId: string | null
  endpoints: ConversationTreeMessageActionEndpoints
  availableActions: ConversationTreeActionKind[]
}

export type ConversationTreeMessageWriteActionKind = 'branch' | 'edit' | 'retry' | 'fork'
export type MessageActionForkOption = 'directPath' | 'includeBranches' | 'targetLevel'

export interface ApplyConversationTreeMessageActionInput {
  action: ConversationTreeMessageWriteActionKind
  content?: string | null
  title?: string | null
  option?: MessageActionForkOption | null
  includeDeleted?: boolean
  statuses?: string[] | null
  metadata?: Record<string, unknown> | null
  signal?: AbortSignal
}

export interface ConversationTreeMessage {
  id: string | null
  conversationId: string | null
  role: string
  content: string
  publicId: string
  parentMessageId: string | null
  branchId: string | null
  status: string
  provider: string | null
  model: string | null
  createdAt: string | null
  metadata: Record<string, unknown>
}

export interface ConversationTreeConversation {
  id: string | null
  title: string
  status: string | null
  model: string | null
  createdAt: string | null
  updatedAt: string | null
  deletedAt: string | null
  metadata: Record<string, unknown>
}

export interface ConversationTreeLocation {
  message: ConversationTreeMessage | null
  path: ConversationTreeMessage[]
  context: ConversationTreeMessage[]
}

export interface ConversationTreeSearchResult {
  message: ConversationTreeMessage
  path: ConversationTreeMessage[]
  context: ConversationTreeMessage[]
}

export interface ConversationTreeBranchSnapshot extends ConversationTreeLocation {
  children: ConversationTreeMessage[]
  searchResults: ConversationTreeSearchResult[]
}

export interface MessageActionResult {
  action: ConversationTreeMessageWriteActionKind
  message: ConversationTreeMessage | null
  path: ConversationTreeMessage[]
  children: ConversationTreeMessage[]
  siblings: ConversationTreeMessage[]
  branchId: string | null
  conversation: ConversationTreeConversation | null
  messages: ConversationTreeMessage[]
  sourceToForkedId: Record<string, string>
}

export interface ConversationTreeFetchOptions {
  signal?: AbortSignal
  limit?: number
  before?: number
  after?: number
  branchId?: string | null
  searchQuery?: string | null
  searchLimit?: number
  includePath?: boolean
  contextBefore?: number
  contextAfter?: number
  includeDeleted?: boolean
  statuses?: string[]
}

const TRAINING_RUNTIME_MODES = new Set<TrainingRuntimeMode>(['text', 'voice', 'video', 'realtime'])
const STAKEHOLDER_API_BASE = '/api/v1/stakeholder'
const TRAINING_STUDIO_API_BASE = '/api/v1/training-studio'
const CONVERSATION_API_BASE = '/api/v1/conversations'
const STAKEHOLDER_ROOM_PROVIDER = 'talkwise-stakeholder-room'
const PIPECAT_REALTIME_PROVIDER = 'pipecat'
const MESSAGE_TREE_REPLAY_METADATA_KEYS = new Set([
  'selectedPath',
  'selected_path',
  'messageTreeSelection',
  'message_tree_selection',
])
const MESSAGE_TREE_TAIL_METADATA_KEYS = new Set([
  'currentBranchTail',
  'current_branch_tail',
])
const SCORING_GROWTH_COMPLETION_METADATA_KEYS = new Set([
  'score',
  'score_id',
  'score_status',
  'overall_score',
  'evaluation',
  'evaluation_id',
  'growth',
  'growth_report',
  'report',
  'report_id',
  'completion',
  'completion_status',
  'completed',
  'completed_at',
])

export function normalizeConversationRef(
  input: ConversationRefInput,
  fallbackProvider = STAKEHOLDER_ROOM_PROVIDER,
): ConversationRef {
  const provider = cleanText(input.provider) ?? fallbackProvider
  const conversationId = cleanText(input.conversationId ?? input.conversation_id)
  if (!provider) {
    throw new Error('conversation provider cannot be empty')
  }
  if (!conversationId) {
    throw new Error('conversationId cannot be empty')
  }

  return {
    provider,
    conversationId,
    branchTailMessageId: cleanText(input.branchTailMessageId ?? input.branch_tail_message_id),
    legacyRoomId: cleanText(input.legacyRoomId ?? input.legacy_room_id),
    metadata: cloneMetadata(input.metadata),
  }
}

export function normalizeTrainingTurn(input: TrainingTurnInput): TrainingTurn {
  const text = cleanText(input.text ?? input.content)
  if (!text) {
    throw new Error('training turn text cannot be empty')
  }

  const role = roleForTurn(input)
  return {
    turnId: cleanText(input.turnId ?? input.turn_id ?? input.messageId ?? input.message_id ?? input.id),
    role,
    speaker: speakerForRole(role),
    sender: senderForRole(role),
    senderId: cleanText(input.senderId ?? input.sender_id),
    text,
    content: text,
    metadata: cloneMetadata(input.metadata),
    parentMessageId: cleanText(input.parentMessageId ?? input.parent_message_id),
    branchId: cleanText(input.branchId ?? input.branch_id),
    provider: cleanText(input.provider),
    model: cleanText(input.model),
    modelSpec: cleanText(input.modelSpec ?? input.model_spec),
  }
}

export function buildTrainingConversationPayload(
  input: BuildTrainingConversationPayloadInput,
): TrainingConversationPayload {
  const mode = normalizeRuntimeMode(input.mode)
  const provider = normalizeProvider(input.provider ?? input.conversation.provider, mode)
  const conversation = normalizeConversationRef({ ...input.conversation, provider }, provider)
  const turns = normalizeTrainingTurnsForConversation(
    input.turns ?? (input.turn ? [input.turn] : []),
    conversation,
    provider,
  )
  const endpoint = cleanText(input.endpoint) ?? resolveRuntimeEndpoint({
    mode,
    provider,
    conversation,
    roomId: input.roomId,
    sessionId: input.sessionId,
    transport: input.endpointTransport,
  })

  return {
    mode,
    provider,
    endpoint,
    conversation,
    turns,
    metadata: cloneMetadata(input.metadata),
  }
}

export function buildConversationTreeMessageActionContext(
  input: ConversationTreeMessageActionContextInput,
): ConversationTreeMessageActionContext | null {
  const metadata = cloneMetadata(input.metadata)
  const metadataConversation = recordValue(metadata.conversation)
    ?? recordValue(metadata.conversationRef)
    ?? recordValue(metadata.conversation_ref)
  const metadataMessage = recordValue(metadata.message)
    ?? recordValue(metadata.messageRef)
    ?? recordValue(metadata.message_ref)
  const turnMetadata = cloneMetadata(input.turn?.metadata)

  const provider = cleanText(
    input.provider
      ?? input.conversation?.provider
      ?? metadataRecordText(metadataConversation, 'provider'),
  )
    ?? cleanText(
      metadataText(
        metadata,
        'conversationProvider',
        'conversation_provider',
        'trainingConversationProvider',
        'training_conversation_provider',
        'provider',
      ),
  )
  if (!provider || !isConversationTreeProvider(provider)) return null

  const conversationId = cleanText(
    input.conversationId
      ?? input.conversation_id
      ?? input.conversation?.conversationId
      ?? input.conversation?.conversation_id
      ?? metadataText(metadata, 'conversationId', 'conversation_id')
      ?? metadataRecordText(metadataConversation, 'conversationId', 'conversation_id'),
  )
  if (!conversationId) return null

  const branchId = cleanText(
    input.branchId
      ?? input.branch_id
      ?? input.turn?.branchId
      ?? input.turn?.branch_id
      ?? metadataText(metadata, 'branchId', 'branch_id')
      ?? metadataRecordText(metadataConversation, 'branchId', 'branch_id')
      ?? metadataText(turnMetadata, 'branchId', 'branch_id'),
  )
  const messagePublicId = cleanPublicMessageId(
    input.messagePublicId
      ?? input.message_public_id
      ?? metadataText(metadata, 'messagePublicId', 'message_public_id', 'publicId', 'public_id')
      ?? metadataRecordText(metadataMessage, 'messagePublicId', 'message_public_id', 'publicId', 'public_id')
      ?? metadataText(turnMetadata, 'messagePublicId', 'message_public_id', 'publicId', 'public_id')
      ?? input.conversation?.branchTailMessageId
      ?? input.conversation?.branch_tail_message_id
      ?? metadataRecordText(metadataConversation, 'branchTailMessageId', 'branch_tail_message_id'),
  )
  if (!messagePublicId) return null

  const conversationPath = `${CONVERSATION_API_BASE}/${encodeURIComponent(conversationId)}`
  const messagePath = `${conversationPath}/messages/${encodeURIComponent(messagePublicId)}`
  return {
    provider,
    conversationId,
    messagePublicId,
    branchId,
    endpoints: {
      actions: `${messagePath}/actions`,
      locate: `${messagePath}/locate`,
      path: `${messagePath}/path`,
      children: `${messagePath}/children`,
      fork: `${messagePath}/fork`,
      edit: `${messagePath}/edit`,
      retry: `${messagePath}/retry`,
      search: `${conversationPath}/messages/search`,
    },
    availableActions: ['branch', 'locate', 'path', 'children', 'search', 'edit', 'retry', 'fork'],
  }
}

export async function fetchConversationTreeMessagePath(
  context: ConversationTreeMessageActionContext,
  options: ConversationTreeFetchOptions = {},
): Promise<ConversationTreeMessage[]> {
  const data = await fetchConversationTreeData(
    appendUrlQuery(context.endpoints.path, [
      ['limit', options.limit],
      ['include_deleted', options.includeDeleted],
      ...statusParams(options.statuses),
    ]),
    options.signal,
  )
  return normalizeConversationTreeMessageList(data)
}

export async function fetchConversationTreeMessageChildren(
  context: ConversationTreeMessageActionContext,
  options: ConversationTreeFetchOptions = {},
): Promise<ConversationTreeMessage[]> {
  const data = await fetchConversationTreeData(
    appendUrlQuery(context.endpoints.children, [
      ['include_deleted', options.includeDeleted],
      ...statusParams(options.statuses),
    ]),
    options.signal,
  )
  return normalizeConversationTreeMessageList(data)
}

export async function fetchConversationTreeMessageLocation(
  context: ConversationTreeMessageActionContext,
  options: ConversationTreeFetchOptions = {},
): Promise<ConversationTreeLocation> {
  const data = await fetchConversationTreeData(
    appendUrlQuery(context.endpoints.locate, [
      ['before', options.before],
      ['after', options.after],
    ]),
    options.signal,
  )
  return normalizeConversationTreeLocation(data)
}

export async function searchConversationTreeMessages(
  context: ConversationTreeMessageActionContext,
  options: ConversationTreeFetchOptions = {},
): Promise<ConversationTreeSearchResult[]> {
  const query = cleanText(options.searchQuery)
  if (!query) return []

  const data = await fetchConversationTreeData(
    appendUrlQuery(context.endpoints.search, [
      ['q', query],
      ['limit', options.searchLimit ?? options.limit],
      ['include_path', options.includePath],
      ['context_before', options.contextBefore],
      ['context_after', options.contextAfter],
      ['branch_id', options.branchId],
      ...statusParams(options.statuses),
    ]),
    options.signal,
  )
  return normalizeConversationTreeSearchResults(data)
}

export async function fetchConversationTreeBranchSnapshot(
  context: ConversationTreeMessageActionContext,
  options: ConversationTreeFetchOptions = {},
): Promise<ConversationTreeBranchSnapshot> {
  const searchQuery = cleanText(options.searchQuery)
  const [location, children, searchResults] = await Promise.all([
    fetchConversationTreeMessageLocation(context, {
      ...options,
      before: options.before ?? 2,
      after: options.after ?? 2,
    }),
    fetchConversationTreeMessageChildren(context, options),
    searchQuery
      ? searchConversationTreeMessages(context, {
        ...options,
        searchQuery,
        searchLimit: options.searchLimit ?? 8,
        includePath: options.includePath ?? true,
        contextBefore: options.contextBefore ?? 1,
        contextAfter: options.contextAfter ?? 1,
      })
      : Promise.resolve([]),
  ])

  return {
    ...location,
    children,
    searchResults,
  }
}

export async function applyConversationTreeMessageAction(
  context: ConversationTreeMessageActionContext,
  input: ApplyConversationTreeMessageActionInput,
): Promise<MessageActionResult> {
  const body = buildConversationTreeMessageActionPayload(input)
  const data = await postConversationTreeData(context.endpoints.actions, body, input.signal)
  return normalizeMessageActionResult(data)
}

export function resolveRuntimeEndpoint(options: ResolveRuntimeEndpointOptions): string {
  const mode = normalizeRuntimeMode(options.mode)
  const provider = normalizeProvider(options.provider ?? options.conversation?.provider, mode)
  const transport = options.transport ?? defaultTransport(mode)

  if (transport === 'session') {
    const sessionId = cleanText(options.sessionId)
    return `${TRAINING_STUDIO_API_BASE}/sessions/${sessionId ? encodeURIComponent(sessionId) : ':sessionId'}`
  }

  if (transport === 'realtime_websocket') {
    return `${TRAINING_STUDIO_API_BASE}/realtime${trainingRealtimeQuery(options, provider)}`
  }

  if (isConversationTreeProvider(provider)) {
    const conversationId = cleanText(options.conversation?.conversationId ?? options.conversation?.conversation_id)
    return `${CONVERSATION_API_BASE}/${encodeURIComponent(conversationId ?? ':conversationId')}/chat`
  }

  return `${STAKEHOLDER_API_BASE}/rooms/${encodeURIComponent(resolveRoomId(options, provider) ?? ':roomId')}/messages`
}

function normalizeRuntimeMode(mode: TrainingRuntimeMode): TrainingRuntimeMode {
  if (TRAINING_RUNTIME_MODES.has(mode)) return mode
  throw new Error(`unsupported training runtime mode: ${String(mode)}`)
}

async function fetchConversationTreeData(endpoint: string, signal?: AbortSignal): Promise<unknown> {
  const resp = await fetch(endpoint, { signal })
  if (!resp.ok) {
    throw new Error(await conversationTreeErrorMessage(resp, 'Failed to fetch conversation tree data'))
  }
  const json = await resp.json() as { data?: unknown }
  return json.data
}

async function postConversationTreeData(
  endpoint: string,
  body: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<unknown> {
  const resp = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok) {
    throw new Error(await conversationTreeErrorMessage(resp, 'Failed to apply conversation tree action'))
  }
  const json = await resp.json() as { data?: unknown }
  return json.data
}

async function conversationTreeErrorMessage(resp: Response, fallback: string): Promise<string> {
  const statusFallback = `${fallback}: ${resp.status}`
  try {
    const text = await resp.text()
    if (!text) return statusFallback
    try {
      const detail = errorMessageFromPayload(JSON.parse(text))
      return detail ? `${statusFallback} - ${detail}` : statusFallback
    } catch {
      return `${statusFallback} - ${text.slice(0, 240)}`
    }
  } catch {
    return statusFallback
  }
}

function errorMessageFromPayload(value: unknown): string | null {
  const data = recordValue(value)
  if (!data) return cleanText(value)

  const error = data.error
  const errorRecord = recordValue(error)
  const plainError = typeof error === 'string' || typeof error === 'number' ? error : null
  return cleanText(errorRecord?.message ?? errorRecord?.detail ?? errorRecord?.error)
    ?? cleanText(data.message ?? data.detail ?? plainError)
}

function buildConversationTreeMessageActionPayload(
  input: ApplyConversationTreeMessageActionInput,
): Record<string, unknown> {
  const action = normalizeMessageWriteAction(input.action)
  const payload: Record<string, unknown> = { action }
  const metadata = sanitizeMessageTreeActionMetadata(input.metadata)
  if (Object.keys(metadata).length > 0) payload.metadata = metadata

  if (action === 'edit') {
    const content = cleanText(input.content)
    if (!content) throw new Error('edit action content cannot be empty')
    payload.content = content
  }

  if (action === 'retry') {
    payload.content = input.content === undefined || input.content === null ? '' : String(input.content)
  }

  if (action === 'fork') {
    const title = cleanText(input.title)
    if (title) payload.title = title
    payload.option = normalizeForkOption(input.option) ?? 'targetLevel'
  }

  if (action === 'branch' || action === 'fork') {
    if (input.includeDeleted !== undefined) payload.include_deleted = input.includeDeleted
    const statuses = normalizeStatuses(input.statuses)
    if (statuses.length > 0) payload.statuses = statuses
  }

  return payload
}

function normalizeConversationTreeMessageList(value: unknown): ConversationTreeMessage[] {
  if (!Array.isArray(value)) return []
  return value.map(normalizeConversationTreeMessage).filter((message): message is ConversationTreeMessage => Boolean(message))
}

function normalizeConversationTreeLocation(value: unknown): ConversationTreeLocation {
  const data = recordValue(value)
  const message = normalizeConversationTreeMessage(data?.message)
  return {
    message,
    path: normalizeConversationTreeMessageList(data?.path),
    context: normalizeConversationTreeMessageList(data?.context),
  }
}

function normalizeConversationTreeSearchResults(value: unknown): ConversationTreeSearchResult[] {
  if (!Array.isArray(value)) return []
  const results: ConversationTreeSearchResult[] = []
  for (const item of value) {
    const data = recordValue(item)
    const message = normalizeConversationTreeMessage(data?.message)
    if (!message) continue
    results.push({
      message,
      path: normalizeConversationTreeMessageList(data?.path),
      context: normalizeConversationTreeMessageList(data?.context),
    })
  }
  return results
}

function normalizeMessageActionResult(value: unknown): MessageActionResult {
  const data = recordValue(value) ?? {}
  const action = normalizeMessageWriteAction(data.action)
  return {
    action,
    message: normalizeConversationTreeMessage(data.message),
    path: normalizeConversationTreeMessageList(data.path),
    children: normalizeConversationTreeMessageList(data.children),
    siblings: normalizeConversationTreeMessageList(data.siblings),
    branchId: cleanText(data.branchId ?? data.branch_id),
    conversation: normalizeConversationTreeConversation(data.conversation),
    messages: normalizeConversationTreeMessageList(data.messages),
    sourceToForkedId: normalizeStringRecord(data.sourceToForkedId ?? data.source_to_forked_id),
  }
}

export function getMessageActionResultPath(result: MessageActionResult): ConversationTreeMessage[] {
  if (result.path.length > 0) return result.path
  if (result.messages.length > 0) {
    return buildPathFromMessageList(result.messages, result.message)
  }
  return result.message ? [result.message] : []
}

function buildPathFromMessageList(
  messages: ConversationTreeMessage[],
  selectedMessage: ConversationTreeMessage | null,
): ConversationTreeMessage[] {
  if (!selectedMessage) return messages

  const messagesByPublicId = new Map(messages.map((message) => [message.publicId, message]))
  const firstMessage = messagesByPublicId.get(selectedMessage.publicId) ?? selectedMessage
  const path: ConversationTreeMessage[] = []
  const seen = new Set<string>()
  let current: ConversationTreeMessage | undefined = firstMessage

  while (current && !seen.has(current.publicId)) {
    path.unshift(current)
    seen.add(current.publicId)
    current = current.parentMessageId ? messagesByPublicId.get(current.parentMessageId) : undefined
  }

  if (path.length > 0 && path[path.length - 1]?.publicId === selectedMessage.publicId) {
    return path
  }

  const selectedIndex = messages.findIndex((message) => message.publicId === selectedMessage.publicId)
  return selectedIndex >= 0 ? messages.slice(0, selectedIndex + 1) : messages
}

function normalizeConversationTreeMessage(value: unknown): ConversationTreeMessage | null {
  const data = recordValue(value)
  if (!data) return null
  const publicId = cleanPublicMessageId(data.publicId ?? data.public_id)
  if (!publicId) return null

  return {
    id: cleanText(data.id),
    conversationId: cleanText(data.conversationId ?? data.conversation_id),
    role: cleanText(data.role) ?? 'user',
    content: cleanText(data.content ?? data.text ?? data.message) ?? '',
    publicId,
    parentMessageId: cleanText(data.parentMessageId ?? data.parent_message_id),
    branchId: cleanText(data.branchId ?? data.branch_id),
    status: cleanText(data.status) ?? 'active',
    provider: cleanText(data.provider),
    model: cleanText(data.model),
    createdAt: cleanText(data.createdAt ?? data.created_at),
    metadata: cloneMetadata(recordValue(data.metadata)),
  }
}

function normalizeConversationTreeConversation(value: unknown): ConversationTreeConversation | null {
  const data = recordValue(value)
  if (!data) return null

  return {
    id: cleanText(data.id),
    title: cleanText(data.title) ?? '',
    status: cleanText(data.status),
    model: cleanText(data.model),
    createdAt: cleanText(data.createdAt ?? data.created_at),
    updatedAt: cleanText(data.updatedAt ?? data.updated_at),
    deletedAt: cleanText(data.deletedAt ?? data.deleted_at),
    metadata: cloneMetadata(recordValue(data.metadata)),
  }
}

function appendUrlQuery(
  endpoint: string,
  params: Array<[string, string | number | boolean | null | undefined]>,
): string {
  const searchParams = new URLSearchParams()
  for (const [key, value] of params) {
    if (value === null || value === undefined || value === '') continue
    searchParams.append(key, String(value))
  }
  const query = searchParams.toString()
  return query ? `${endpoint}?${query}` : endpoint
}

function statusParams(statuses: string[] | undefined): Array<[string, string]> {
  return normalizeStatuses(statuses)
    .map((status) => ['statuses', status])
}

function normalizeStatuses(statuses: string[] | null | undefined): string[] {
  if (!statuses) return []
  return statuses
    .map((status) => cleanText(status))
    .filter((status): status is string => Boolean(status))
}

function normalizeProvider(provider: string | null | undefined, mode: TrainingRuntimeMode): string {
  const fallback = mode === 'realtime' ? PIPECAT_REALTIME_PROVIDER : STAKEHOLDER_ROOM_PROVIDER
  if (mode === 'realtime') return PIPECAT_REALTIME_PROVIDER
  return cleanText(provider) ?? fallback
}

function defaultTransport(mode: TrainingRuntimeMode): TrainingRuntimeTransport {
  if (mode !== 'realtime') return 'message'
  return 'realtime_websocket'
}

function trainingRealtimeQuery(options: ResolveRuntimeEndpointOptions, provider?: string): string {
  const params = new URLSearchParams()
  const sessionId = cleanText(options.sessionId)
  const roomId = cleanText(options.roomId)
    ?? cleanText(options.conversation?.legacyRoomId ?? options.conversation?.legacy_room_id)
  if (sessionId) params.set('session_id', sessionId)
  if (roomId) params.set('room_id', roomId)
  if (provider) params.set('provider', provider)
  const query = params.toString()
  return query ? `?${query}` : ''
}

function resolveRoomId(options: ResolveRuntimeEndpointOptions, provider: string): string | null {
  const explicitRoomId = cleanText(options.roomId)
  if (explicitRoomId) return explicitRoomId

  const conversation = options.conversation
  const legacyRoomId = cleanText(conversation?.legacyRoomId ?? conversation?.legacy_room_id)
  if (legacyRoomId) return legacyRoomId

  if (isStakeholderRoomProvider(provider)) {
    return cleanText(conversation?.conversationId ?? conversation?.conversation_id)
  }

  return null
}

function isStakeholderRoomProvider(provider: string): boolean {
  const normalized = normalizeToken(provider)
  return normalized === 'talkwise_stakeholder_room'
    || normalized === 'stakeholder_room'
    || normalized === 'stakeholder'
    || normalized === 'talkwise'
}

function isConversationTreeProvider(provider: string): boolean {
  const normalized = normalizeToken(provider)
  return normalized === 'talkwise_conversation'
    || normalized === 'conversation'
    || normalized === 'message_tree'
    || normalized === 'conversation_tree'
    || normalized === 'conversation_message_tree'
}

function normalizeTrainingTurnsForConversation(
  inputTurns: TrainingTurnInput[],
  conversation: ConversationRef,
  provider: string,
): TrainingTurn[] {
  const turns = inputTurns.map(normalizeTrainingTurn)
  if (!isConversationTreeProvider(provider)) return turns
  return turns.map((turn, index) => ({
    ...turn,
    parentMessageId: turn.parentMessageId ?? (index === 0 ? conversation.branchTailMessageId : null),
    branchId: turn.branchId ?? metadataText(conversation.metadata, 'branchId', 'branch_id'),
  }))
}

function roleForTurn(input: TrainingTurnInput): TrainingTurnRole {
  return roleFromValue(input.role)
    ?? roleFromValue(input.senderType ?? input.sender_type ?? input.sender)
    ?? roleFromValue(input.speaker)
    ?? 'user'
}

function roleFromValue(value: string | null | undefined): TrainingTurnRole | null {
  const normalized = normalizeToken(value)
  if (!normalized) return null
  if (
    normalized === 'assistant'
    || normalized === 'persona'
    || normalized === 'counterpart'
    || normalized === 'ai'
    || normalized === 'agent'
  ) {
    return 'assistant'
  }
  if (
    normalized === 'system'
    || normalized === 'coach'
    || normalized === 'training_coach'
  ) {
    return 'system'
  }
  if (
    normalized === 'user'
    || normalized === 'candidate'
    || normalized === 'learner'
    || normalized === 'human'
  ) {
    return 'user'
  }
  return null
}

function senderForRole(role: TrainingTurnRole): TalkWiseSender {
  if (role === 'assistant') return 'persona'
  if (role === 'system') return 'system'
  return 'user'
}

function speakerForRole(role: TrainingTurnRole): TrainingTranscriptSpeaker {
  if (role === 'assistant') return 'counterpart'
  if (role === 'system') return 'system'
  return 'user'
}

function normalizeToken(value: string | null | undefined): string | null {
  return cleanText(value)?.toLowerCase().replace(/[\s-]+/g, '_') ?? null
}

function metadataKeyToken(value: string): string {
  return value
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[\s-]+/g, '_')
    .toLowerCase()
}

function isScoringGrowthCompletionMetadataKey(value: string): boolean {
  return SCORING_GROWTH_COMPLETION_METADATA_KEYS.has(metadataKeyToken(value))
}

function cloneMetadataValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneMetadataValue)
  const record = recordValue(value)
  if (!record) return value
  return Object.fromEntries(
    Object.entries(record).map(([key, nestedValue]) => [key, cloneMetadataValue(nestedValue)]),
  )
}

function sanitizeReplayMetadataValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeReplayMetadataValue)
  const record = recordValue(value)
  if (!record) return value

  const sanitized: Record<string, unknown> = {}
  for (const [key, nestedValue] of Object.entries(record)) {
    if (isScoringGrowthCompletionMetadataKey(key)) continue
    sanitized[key] = sanitizeReplayMetadataValue(nestedValue)
  }
  return sanitized
}

function normalizeReplayMetadataRecord(value: unknown, replayOnly: boolean): unknown {
  const record = recordValue(value)
  if (!record) return cloneMetadataValue(value)
  const normalized = sanitizeReplayMetadataValue(record) as Record<string, unknown>
  if (replayOnly) {
    normalized.purpose = 'training_replay_context'
    normalized.replayContextOnly = true
    normalized.affectsScoring = false
    normalized.affectsCompletion = false
  }
  return normalized
}

function normalizeMessageTreeReplayMetadata(
  metadata: Record<string, unknown>,
): Record<string, unknown> {
  const normalized = cloneMetadataValue(metadata) as Record<string, unknown>
  for (const key of Object.keys(normalized)) {
    if (MESSAGE_TREE_REPLAY_METADATA_KEYS.has(key)) {
      normalized[key] = normalizeReplayMetadataRecord(normalized[key], true)
    } else if (MESSAGE_TREE_TAIL_METADATA_KEYS.has(key)) {
      normalized[key] = normalizeReplayMetadataRecord(normalized[key], false)
    }
  }
  return normalized
}

function sanitizeMessageTreeActionMetadata(
  metadata: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const sanitized: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(metadata ?? {})) {
    if (isScoringGrowthCompletionMetadataKey(key)) continue
    sanitized[key] = cloneMetadataValue(value)
  }
  return normalizeMessageTreeReplayMetadata(sanitized)
}

function normalizeMessageWriteAction(value: unknown): ConversationTreeMessageWriteActionKind {
  const normalized = normalizeToken(cleanText(value))
  if (normalized === 'branch' || normalized === 'edit' || normalized === 'retry' || normalized === 'fork') {
    return normalized
  }
  throw new Error(`unsupported conversation tree message action: ${String(value)}`)
}

function normalizeForkOption(value: unknown): MessageActionForkOption | null {
  const text = cleanText(value)
  if (text === 'directPath' || text === 'includeBranches' || text === 'targetLevel') return text
  return null
}

function cleanText(value: unknown): string | null {
  if (value === undefined || value === null) return null
  const text = String(value).trim()
  return text || null
}

function cleanPublicMessageId(value: unknown): string | null {
  const text = cleanText(value)
  if (!text || /^\d+$/.test(text)) return null
  return text
}

function cloneMetadata(value: Record<string, unknown> | null | undefined): Record<string, unknown> {
  return value ? { ...value } : {}
}

function metadataText(metadata: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = cleanText(metadata[key])
    if (value) return value
  }
  return null
}

function metadataRecordText(metadata: Record<string, unknown> | null, ...keys: string[]): string | null {
  return metadata ? metadataText(metadata, ...keys) : null
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function normalizeStringRecord(value: unknown): Record<string, string> {
  const data = recordValue(value)
  if (!data) return {}
  const result: Record<string, string> = {}
  for (const [key, rawValue] of Object.entries(data)) {
    const text = cleanText(rawValue)
    if (text) result[key] = text
  }
  return result
}
