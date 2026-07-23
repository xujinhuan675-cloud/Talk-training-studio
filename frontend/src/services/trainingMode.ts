export type TrainingMode = 'text' | 'voice' | 'video'
export type NormalizedTrainingMode = TrainingMode
export type InteractionMode = 'turn_based' | 'realtime'
export type TrainingProfile = 'practice' | 'live_coach'
export type TrainingFeedbackMode = 'simulation' | 'assisted' | 'drill'
export type LegacyTrainingMode = TrainingMode | 'realtime'

export const TRAINING_MODE_QUERY_PARAM = 'trainingMode'
export const INTERACTION_MODE_QUERY_PARAM = 'interactionMode'
export const TRAINING_PROFILE_QUERY_PARAM = 'trainingProfile'
export const TRAINING_FEEDBACK_MODE_QUERY_PARAM = 'trainingFeedbackMode'
export const REPLY_LANGUAGE_QUERY_PARAM = 'replyLanguage'
export const SOURCE_LANGUAGE_QUERY_PARAM = 'sourceLanguage'
export const TARGET_LANGUAGE_QUERY_PARAM = 'targetLanguage'
const CONVERSATION_ROUTE_PREFIX = '/conversations'

const TRAINING_MODES = new Set<NormalizedTrainingMode>(['text', 'voice', 'video'])
const INTERACTION_MODES = new Set<InteractionMode>(['turn_based', 'realtime'])
const TRAINING_PROFILES = new Set<TrainingProfile>(['practice', 'live_coach'])
const TRAINING_FEEDBACK_MODES = new Set<TrainingFeedbackMode>(['simulation', 'assisted', 'drill'])
const DEFAULT_TRAINING_FEEDBACK_MODE: TrainingFeedbackMode = 'simulation'

export interface TrainingModeLocationState {
  source?: string
  trainingMode?: LegacyTrainingMode
  interactionMode?: InteractionMode
  trainingSessionId?: string
  trainingProfile?: TrainingProfile
  trainingFeedbackMode?: TrainingFeedbackMode
  replyLanguage?: string
  sourceLanguage?: string
  targetLanguage?: string
}

export interface TrainingModeChatPathOptions {
  trainingProfile?: TrainingProfile | null
  trainingFeedbackMode?: TrainingFeedbackMode | null
  replyLanguage?: string | null
  sourceLanguage?: string | null
  targetLanguage?: string | null
}

function normalizeTrainingMode(value: unknown): NormalizedTrainingMode | null {
  if (value === 'realtime') return 'voice'
  return typeof value === 'string' && TRAINING_MODES.has(value as NormalizedTrainingMode)
    ? value as NormalizedTrainingMode
    : null
}

function isInteractionMode(value: unknown): value is InteractionMode {
  return typeof value === 'string' && INTERACTION_MODES.has(value as InteractionMode)
}

function normalizeTrainingProfile(value: unknown): TrainingProfile | null {
  return typeof value === 'string' && TRAINING_PROFILES.has(value as TrainingProfile)
    ? value as TrainingProfile
    : null
}

function normalizeTrainingFeedbackMode(value: unknown): TrainingFeedbackMode | null {
  return typeof value === 'string' && TRAINING_FEEDBACK_MODES.has(value as TrainingFeedbackMode)
    ? value as TrainingFeedbackMode
    : null
}

function normalizeLanguage(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function getStateValue(state: unknown, key: keyof TrainingModeLocationState): unknown {
  return state && typeof state === 'object' && key in state
    ? (state as TrainingModeLocationState)[key]
    : undefined
}

export function buildTrainingModeChatPath(
  roomId: number | string,
  mode: LegacyTrainingMode,
  trainingSessionId?: string | null,
  interactionMode?: InteractionMode | null,
  options: TrainingModeChatPathOptions = {},
): string {
  const legacyMode = mode as LegacyTrainingMode
  const normalizedMode = normalizeTrainingMode(legacyMode)
  const resolvedInteractionMode = interactionMode ?? (legacyMode === 'realtime' ? 'realtime' : 'turn_based')
  const params = new URLSearchParams({
    [TRAINING_MODE_QUERY_PARAM]: normalizedMode ?? 'voice',
    [INTERACTION_MODE_QUERY_PARAM]: resolvedInteractionMode,
  })
  if (trainingSessionId) {
    params.set('trainingSessionId', trainingSessionId)
  }
  const trainingProfile = normalizeTrainingProfile(options.trainingProfile)
  if (trainingProfile && trainingProfile !== 'practice') {
    params.set(TRAINING_PROFILE_QUERY_PARAM, trainingProfile)
  }
  const trainingFeedbackMode = normalizeTrainingFeedbackMode(options.trainingFeedbackMode)
  if (trainingFeedbackMode && trainingFeedbackMode !== DEFAULT_TRAINING_FEEDBACK_MODE) {
    params.set(TRAINING_FEEDBACK_MODE_QUERY_PARAM, trainingFeedbackMode)
  }
  const replyLanguage = normalizeLanguage(options.replyLanguage)
  if (replyLanguage) {
    params.set(REPLY_LANGUAGE_QUERY_PARAM, replyLanguage)
  }
  const sourceLanguage = normalizeLanguage(options.sourceLanguage)
  const targetLanguage = normalizeLanguage(options.targetLanguage)
  if (sourceLanguage) {
    params.set(SOURCE_LANGUAGE_QUERY_PARAM, sourceLanguage)
  }
  if (targetLanguage) {
    params.set(TARGET_LANGUAGE_QUERY_PARAM, targetLanguage)
  }
  return `${CONVERSATION_ROUTE_PREFIX}/${roomId}?${params.toString()}`
}

export function getTrainingModeFromLocation(search: string, state: unknown): NormalizedTrainingMode | null {
  const modeFromQuery = new URLSearchParams(search).get(TRAINING_MODE_QUERY_PARAM)
  const normalizedModeFromQuery = normalizeTrainingMode(modeFromQuery)
  if (normalizedModeFromQuery) {
    return normalizedModeFromQuery
  }

  const normalizedModeFromState = normalizeTrainingMode(getStateValue(state, 'trainingMode'))
  if (normalizedModeFromState) {
    return normalizedModeFromState
  }

  return null
}

export function getInteractionModeFromLocation(search: string, state: unknown): InteractionMode {
  const searchParams = new URLSearchParams(search)
  const interactionModeFromQuery = searchParams.get(INTERACTION_MODE_QUERY_PARAM)
  if (isInteractionMode(interactionModeFromQuery)) {
    return interactionModeFromQuery
  }

  if (searchParams.get(TRAINING_MODE_QUERY_PARAM) === 'realtime') {
    return 'realtime'
  }

  const interactionModeFromState = getStateValue(state, 'interactionMode')
  if (isInteractionMode(interactionModeFromState)) {
    return interactionModeFromState
  }

  return getStateValue(state, 'trainingMode') === 'realtime' ? 'realtime' : 'turn_based'
}

export function getTrainingSessionIdFromLocation(search: string, state: unknown): string | null {
  const sessionIdFromQuery = new URLSearchParams(search).get('trainingSessionId')?.trim()
  if (sessionIdFromQuery) {
    return sessionIdFromQuery
  }

  if (state && typeof state === 'object' && 'trainingSessionId' in state) {
    const sessionIdFromState = (state as TrainingModeLocationState).trainingSessionId
    if (typeof sessionIdFromState === 'string' && sessionIdFromState.trim()) {
      return sessionIdFromState.trim()
    }
  }

  return null
}

export function getTrainingProfileFromLocation(search: string, state: unknown): TrainingProfile {
  const searchParams = new URLSearchParams(search)
  const profileFromQuery = normalizeTrainingProfile(searchParams.get(TRAINING_PROFILE_QUERY_PARAM))
  if (profileFromQuery) {
    return profileFromQuery
  }

  const profileFromState = normalizeTrainingProfile(getStateValue(state, 'trainingProfile'))
  if (profileFromState) {
    return profileFromState
  }

  return getStateValue(state, 'source') === 'live-coach' ? 'live_coach' : 'practice'
}

export function getTrainingFeedbackModeFromLocation(search: string, state: unknown): TrainingFeedbackMode {
  const searchParams = new URLSearchParams(search)
  const feedbackModeFromQuery = normalizeTrainingFeedbackMode(searchParams.get(TRAINING_FEEDBACK_MODE_QUERY_PARAM))
  if (feedbackModeFromQuery) {
    return feedbackModeFromQuery
  }

  const feedbackModeFromState = normalizeTrainingFeedbackMode(getStateValue(state, 'trainingFeedbackMode'))
  if (feedbackModeFromState) {
    return feedbackModeFromState
  }

  return DEFAULT_TRAINING_FEEDBACK_MODE
}

export function getTrainingReplyLanguageFromLocation(search: string, state: unknown): string | null {
  const searchParams = new URLSearchParams(search)
  return normalizeLanguage(searchParams.get(REPLY_LANGUAGE_QUERY_PARAM))
    ?? normalizeLanguage(getStateValue(state, 'replyLanguage'))
}

export function getLiveCoachLanguagePairFromLocation(
  search: string,
  state: unknown,
): { sourceLanguage: string | null; targetLanguage: string | null } {
  const searchParams = new URLSearchParams(search)
  return {
    sourceLanguage: normalizeLanguage(searchParams.get(SOURCE_LANGUAGE_QUERY_PARAM))
      ?? normalizeLanguage(getStateValue(state, 'sourceLanguage')),
    targetLanguage: normalizeLanguage(searchParams.get(TARGET_LANGUAGE_QUERY_PARAM))
      ?? normalizeLanguage(getStateValue(state, 'targetLanguage')),
  }
}

export function isTrainingModeBattlePrep(
  roomType: string | null | undefined,
  mode: LegacyTrainingMode | null,
  expectedMode: LegacyTrainingMode,
  interactionMode?: InteractionMode | null,
  expectedInteractionMode?: InteractionMode | null,
): boolean {
  if (roomType !== 'battle_prep') return false
  const legacyMode = mode as LegacyTrainingMode | null
  const legacyExpectedMode = expectedMode as LegacyTrainingMode
  const normalizedMode = normalizeTrainingMode(legacyMode)
  const normalizedExpectedMode = normalizeTrainingMode(legacyExpectedMode)
  if (!normalizedMode || !normalizedExpectedMode || normalizedMode !== normalizedExpectedMode) return false

  const resolvedInteractionMode = interactionMode ?? (legacyMode === 'realtime' ? 'realtime' : 'turn_based')
  const resolvedExpectedInteractionMode = expectedInteractionMode ?? (legacyExpectedMode === 'realtime' ? 'realtime' : null)
  return resolvedExpectedInteractionMode ? resolvedInteractionMode === resolvedExpectedInteractionMode : true
}
