export type TrainingMode = 'text' | 'voice' | 'video'

export const TRAINING_MODE_QUERY_PARAM = 'trainingMode'

const TRAINING_MODES = new Set<TrainingMode>(['text', 'voice', 'video'])

export interface TrainingModeLocationState {
  source?: string
  trainingMode?: TrainingMode
  trainingSessionId?: string
}

function isTrainingMode(value: unknown): value is TrainingMode {
  return typeof value === 'string' && TRAINING_MODES.has(value as TrainingMode)
}

export function buildTrainingModeChatPath(
  roomId: number | string,
  mode: TrainingMode,
  trainingSessionId?: string | null,
): string {
  const params = new URLSearchParams({ [TRAINING_MODE_QUERY_PARAM]: mode })
  if (trainingSessionId) {
    params.set('trainingSessionId', trainingSessionId)
  }
  return `/chat/${roomId}?${params.toString()}`
}

export function getTrainingModeFromLocation(search: string, state: unknown): TrainingMode | null {
  const modeFromQuery = new URLSearchParams(search).get(TRAINING_MODE_QUERY_PARAM)
  if (isTrainingMode(modeFromQuery)) {
    return modeFromQuery
  }

  if (state && typeof state === 'object' && 'trainingMode' in state) {
    const modeFromState = (state as TrainingModeLocationState).trainingMode
    if (isTrainingMode(modeFromState)) {
      return modeFromState
    }
  }

  return null
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

export function isTrainingModeBattlePrep(
  roomType: string | null | undefined,
  mode: TrainingMode | null,
  expectedMode: TrainingMode,
): boolean {
  return roomType === 'battle_prep' && mode === expectedMode
}
