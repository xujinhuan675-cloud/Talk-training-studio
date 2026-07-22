import type { InteractionMode, TrainingMode } from './trainingMode'
import type { StartTrainingSessionRequest } from './trainingSession'

export interface TrainingLaunchSession {
  session_id: string
}

export interface TrainingLaunchStartedSession {
  session_id: string
  room_id?: number | string | null
}

export interface LaunchTrainingSessionFlowParams<TCreateRequest, TNavigationState> {
  createTrainingSessionRequest: TCreateRequest
  createTrainingSession: (request: TCreateRequest) => Promise<TrainingLaunchSession>
  startRequestData?: StartTrainingSessionRequest
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
    roomId: number | string
    startedSession: TrainingLaunchStartedSession
    trainingSession: TrainingLaunchSession
    trainingMode: TrainingMode
    interactionMode: InteractionMode
  }) => TNavigationState
  navigate: (to: string, options: { state: TNavigationState }) => void
  afterStartSession?: (context: {
    roomId: number | string
    startedSession: TrainingLaunchStartedSession
    trainingSession: TrainingLaunchSession
    trainingMode: TrainingMode
    interactionMode: InteractionMode
  }) => void | Promise<void>
}

export interface LaunchTrainingSessionFlowResult<TNavigationState> {
  trainingSession: TrainingLaunchSession
  startedSession: TrainingLaunchStartedSession
  roomId: number | string
  chatPath: string
  state: TNavigationState
}

export async function launchTrainingSessionFlow<TCreateRequest, TNavigationState>(
  params: LaunchTrainingSessionFlowParams<TCreateRequest, TNavigationState>,
): Promise<LaunchTrainingSessionFlowResult<TNavigationState>> {
  const trainingSession = await params.createTrainingSession(params.createTrainingSessionRequest)
  const startRequest = params.buildTrainingSessionStartRequest(
    params.startRequestData ?? {},
    params.trainingMode,
    params.interactionMode,
  )
  const startedSession = await params.startTrainingSession(trainingSession.session_id, startRequest)
  const roomId = startedSession.room_id
  if (roomId == null) {
    throw new Error('Failed to resolve training room')
  }
  const state = params.buildNavigationState({
    roomId,
    startedSession,
    trainingSession,
    trainingMode: params.trainingMode,
    interactionMode: params.interactionMode,
  })
  await params.afterStartSession?.({
    roomId,
    startedSession,
    trainingSession,
    trainingMode: params.trainingMode,
    interactionMode: params.interactionMode,
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
    startedSession,
    roomId,
    chatPath,
    state,
  }
}
