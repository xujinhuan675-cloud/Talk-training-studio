import type { InteractionMode, TrainingMode } from './trainingMode'
import type { StartTrainingSessionRequest, TrainingSessionDTO } from './trainingSession'

export interface TrainingLaunchStartSessionContext<TRoom extends { id: number | string }> {
  trainingSession: TrainingSessionDTO
  startedSession: TrainingSessionDTO
  room: TRoom | null
  roomId: number | string
  trainingMode: TrainingMode
  interactionMode: InteractionMode
}

export interface TrainingLaunchFlowOptions<
  TCreateRequest,
  TBattlePayload,
  TRoom extends { id: number | string },
  TNavigationState,
> {
  createTrainingSessionRequest: TCreateRequest
  createTrainingSession: (request: TCreateRequest) => Promise<TrainingSessionDTO>
  battlePayload?: TBattlePayload | null
  startBattle?: (payload: TBattlePayload) => Promise<TRoom>
  startTrainingSession: (sessionId: string, request: StartTrainingSessionRequest) => Promise<TrainingSessionDTO>
  buildTrainingSessionStartRequest: (
    request: StartTrainingSessionRequest,
    trainingMode: TrainingMode,
    interactionMode: InteractionMode,
  ) => StartTrainingSessionRequest
  buildChatPath: (
    roomId: number | string,
    trainingMode: TrainingMode,
    trainingSessionId: string,
    interactionMode: InteractionMode,
  ) => string
  buildNavigationState: (context: TrainingLaunchStartSessionContext<TRoom>) => TNavigationState
  navigate: (path: string, options: { state: TNavigationState }) => void
  trainingMode: TrainingMode
  interactionMode: InteractionMode
  afterStartSession?: (context: TrainingLaunchStartSessionContext<TRoom>) => void | Promise<void>
}

export interface TrainingLaunchFlowResult<TNavigationState, TRoom extends { id: number | string }> {
  trainingSession: TrainingSessionDTO
  room: TRoom | null
  startedSession: TrainingSessionDTO
  roomId: number | string
  chatPath: string
  navigationState: TNavigationState
}

export async function launchTrainingSessionFlow<
  TCreateRequest,
  TBattlePayload,
  TRoom extends { id: number | string },
  TNavigationState,
>(
  options: TrainingLaunchFlowOptions<TCreateRequest, TBattlePayload, TRoom, TNavigationState>,
): Promise<TrainingLaunchFlowResult<TNavigationState, TRoom>> {
  const trainingSession = await options.createTrainingSession(options.createTrainingSessionRequest)
  const room = options.battlePayload == null
    ? null
    : options.startBattle
      ? await options.startBattle(options.battlePayload)
      : null
  if (options.battlePayload != null && !options.startBattle) {
    throw new Error('Training launch requires startBattle when a battle payload is provided')
  }

  const startedSession = await options.startTrainingSession(
    trainingSession.session_id,
    options.buildTrainingSessionStartRequest(
      room ? { room_id: room.id } : {},
      options.trainingMode,
      options.interactionMode,
    ),
  )

  const context: TrainingLaunchStartSessionContext<TRoom> = {
    trainingSession,
    startedSession,
    room,
    roomId: startedSession.room_id ?? room?.id ?? null,
    trainingMode: options.trainingMode,
    interactionMode: options.interactionMode,
  }

  if (context.roomId == null) {
    throw new Error('Failed to resolve training room')
  }

  await options.afterStartSession?.(context)

  const chatPath = options.buildChatPath(
    context.roomId,
    options.trainingMode,
    startedSession.session_id,
    options.interactionMode,
  )
  const navigationState = options.buildNavigationState(context)
  options.navigate(chatPath, { state: navigationState })

  return {
    trainingSession,
    room,
    startedSession,
    roomId: context.roomId,
    chatPath,
    navigationState,
  }
}
