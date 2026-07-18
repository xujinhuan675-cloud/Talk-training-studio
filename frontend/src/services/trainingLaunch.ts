import type { InteractionMode, TrainingMode } from './trainingMode'
import type { StartTrainingSessionRequest } from './trainingSession'

export interface TrainingLaunchRoom {
  id: number | string
}

export interface TrainingLaunchSession {
  session_id: string
}

export interface TrainingLaunchStartedSession {
  session_id: string
  room_id?: number | string | null
}

export interface LaunchTrainingSessionFlowParams<TCreateRequest, TBattlePayload, TNavigationState> {
  createTrainingSessionRequest: TCreateRequest
  createTrainingSession: (request: TCreateRequest) => Promise<TrainingLaunchSession>
  battlePayload: TBattlePayload | null
  startBattle: (payload: TBattlePayload) => Promise<TrainingLaunchRoom>
  buildTrainingSessionStartRequest: (
    data: StartTrainingSessionRequest,
    trainingMode: TrainingMode,
    interactionMode: InteractionMode,
  ) => StartTrainingSessionRequest
  startTrainingSession: (
    sessionId: string,
    data: StartTrainingSessionRequest,
  ) => Promise<TrainingLaunchStartedSession>
  trainingMode: TrainingMode
  interactionMode: InteractionMode
  buildChatPath: (
    roomId: number | string,
    trainingMode: TrainingMode,
    trainingSessionId: string,
    interactionMode: InteractionMode,
  ) => string
  buildNavigationState: (context: {
    room: TrainingLaunchRoom | null
    roomId: number | string
    startedSession: TrainingLaunchStartedSession
    trainingSession: TrainingLaunchSession
  }) => TNavigationState
  navigate: (to: string, options: { state: TNavigationState }) => void
  afterStartSession?: (context: {
    room: TrainingLaunchRoom | null
    roomId: number | string
    startedSession: TrainingLaunchStartedSession
    trainingSession: TrainingLaunchSession
  }) => void | Promise<void>
}

export interface LaunchTrainingSessionFlowResult<TNavigationState> {
  trainingSession: TrainingLaunchSession
  room: TrainingLaunchRoom | null
  startedSession: TrainingLaunchStartedSession
  roomId: number | string
  chatPath: string
  state: TNavigationState
}

export async function launchTrainingSessionFlow<TCreateRequest, TNavigationState>(
  params: LaunchTrainingSessionFlowParams<TCreateRequest, unknown, TNavigationState>,
): Promise<LaunchTrainingSessionFlowResult<TNavigationState>> {
  const trainingSession = await params.createTrainingSession(params.createTrainingSessionRequest)
  const room = params.battlePayload == null ? null : await params.startBattle(params.battlePayload)
  const startRequest = params.buildTrainingSessionStartRequest(
    room ? { room_id: room.id } : {},
    params.trainingMode,
    params.interactionMode,
  )
  const startedSession = await params.startTrainingSession(trainingSession.session_id, startRequest)
  const roomId = startedSession.room_id ?? room?.id
  if (roomId == null) {
    throw new Error('Failed to resolve training room')
  }
  const state = params.buildNavigationState({
    room,
    roomId,
    startedSession,
    trainingSession,
  })
  await params.afterStartSession?.({
    room,
    roomId,
    startedSession,
    trainingSession,
  })
  const chatPath = params.buildChatPath(
    roomId,
    params.trainingMode,
    startedSession.session_id,
    params.interactionMode,
  )
  params.navigate(chatPath, { state })
  return {
    trainingSession,
    room,
    startedSession,
    roomId,
    chatPath,
    state,
  }
}
