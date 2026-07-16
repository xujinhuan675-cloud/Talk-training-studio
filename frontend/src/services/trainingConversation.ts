export type TrainingRuntimeMode = 'text' | 'voice' | 'video' | 'realtime'
export type TrainingTurnRole = 'system' | 'user' | 'assistant'
export type TrainingTranscriptSpeaker = 'user' | 'counterpart' | 'system'
export type TalkWiseSender = 'user' | 'persona' | 'system'
export type TrainingRuntimeTransport =
  | 'message'
  | 'session'
  | 'realtime_websocket'
  | 'realtime_sdp'
  | 'realtime_transcripts'

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

const TRAINING_RUNTIME_MODES = new Set<TrainingRuntimeMode>(['text', 'voice', 'video', 'realtime'])
const STAKEHOLDER_API_BASE = '/api/v1/stakeholder'
const TRAINING_STUDIO_API_BASE = '/api/v1/training-studio'
const CONVERSATION_API_BASE = '/api/v1/conversations'
const STAKEHOLDER_ROOM_PROVIDER = 'talkwise-stakeholder-room'
const LOCAL_REALTIME_PROVIDER = 'local'

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

export function resolveRuntimeEndpoint(options: ResolveRuntimeEndpointOptions): string {
  const mode = normalizeRuntimeMode(options.mode)
  const provider = normalizeProvider(options.provider ?? options.conversation?.provider, mode)
  const transport = options.transport ?? defaultTransport(mode, provider)

  if (transport === 'session') {
    const sessionId = cleanText(options.sessionId)
    return `${TRAINING_STUDIO_API_BASE}/sessions/${sessionId ? encodeURIComponent(sessionId) : ':sessionId'}`
  }

  if (transport === 'realtime_transcripts') {
    return `${TRAINING_STUDIO_API_BASE}/realtime/transcripts`
  }

  if (transport === 'realtime_sdp') {
    return `${TRAINING_STUDIO_API_BASE}/realtime/sdp${trainingRealtimeQuery(options)}`
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

function normalizeProvider(provider: string | null | undefined, mode: TrainingRuntimeMode): string {
  const fallback = mode === 'realtime' ? LOCAL_REALTIME_PROVIDER : STAKEHOLDER_ROOM_PROVIDER
  return cleanText(provider) ?? fallback
}

function defaultTransport(mode: TrainingRuntimeMode, provider: string): TrainingRuntimeTransport {
  if (mode !== 'realtime') return 'message'
  return isOpenAIWebRtcProvider(provider) ? 'realtime_sdp' : 'realtime_websocket'
}

function isOpenAIWebRtcProvider(provider: string): boolean {
  const normalized = normalizeToken(provider)
  return normalized === 'openai_webrtc' || normalized === 'webrtc' || normalized === 'openai_sdp'
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

function cleanText(value: unknown): string | null {
  if (value === undefined || value === null) return null
  const text = String(value).trim()
  return text || null
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
