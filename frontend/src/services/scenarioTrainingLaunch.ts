import type { InteractionMode, TrainingFeedbackMode, TrainingMode } from './trainingMode'
import { buildTrainingModeChatPath } from './trainingMode'
import { launchTrainingSessionFlow } from './trainingLaunch'
import {
  buildRoomBackedTrainingSessionStartRequest,
  createTrainingSession,
  startTrainingSession,
} from './trainingSession'
import {
  buildScenarioTrainingRuntimePersona,
  buildScenarioTrainingRouteState,
  buildScenarioTrainingTaskConfig,
  markScenarioTrainingStarted,
  saveScenarioTrainingProgress,
  type ScenarioTrainingCard,
  type ScenarioTrainingProgress,
  type ScenarioTrainingProgressScope,
} from '../data/trainingScenarios'
import { DEFAULT_TRAINING_REPLY_LANGUAGE, normalizeTrainingReplyLanguage } from '../data/trainingReplyLanguages'

export type ScenarioLaunchMode = TrainingMode | 'realtime'

export interface LaunchScenarioTrainingParams {
  scenario: ScenarioTrainingCard
  mode?: ScenarioLaunchMode
  feedbackMode?: TrainingFeedbackMode
  replyLanguage?: string | null
  progress: ScenarioTrainingProgress
  progressScope?: ScenarioTrainingProgressScope
  navigate: (to: string, options: { state: unknown }) => void
  onProgressChange?: (progress: ScenarioTrainingProgress) => void
}

export function getScenarioTrainingMode(mode: ScenarioLaunchMode): TrainingMode {
  return mode === 'realtime' ? 'voice' : mode
}

export function getScenarioInteractionMode(mode: ScenarioLaunchMode): InteractionMode {
  return mode === 'realtime' ? 'realtime' : 'turn_based'
}

export async function launchScenarioTraining({
  scenario,
  mode = 'text',
  feedbackMode = 'simulation',
  replyLanguage = DEFAULT_TRAINING_REPLY_LANGUAGE,
  progress,
  progressScope,
  navigate,
  onProgressChange,
}: LaunchScenarioTrainingParams) {
  const trainingMode = getScenarioTrainingMode(mode)
  const interactionMode = getScenarioInteractionMode(mode)
  const normalizedReplyLanguage = normalizeTrainingReplyLanguage(replyLanguage)
  const scenarioParam = `scenarioTrainingId=${encodeURIComponent(scenario.id)}`
  const taskConfig = buildScenarioTrainingTaskConfig(scenario, {
    feedbackMode,
    replyLanguage: normalizedReplyLanguage,
  })
  const scenarioTrainingMetadata = taskConfig.metadata?.scenario_training
  const scenarioTrainingRecord = scenarioTrainingMetadata
    && typeof scenarioTrainingMetadata === 'object'
    && !Array.isArray(scenarioTrainingMetadata)
    ? scenarioTrainingMetadata as Record<string, unknown>
    : {}

  return launchTrainingSessionFlow({
    createTrainingSessionRequest: {
      mode: trainingMode,
      scenario_template_id: scenario.id,
      user_id: progressScope?.userId,
      team_id: progressScope?.teamId,
      task_config: {
        ...taskConfig,
        metadata: {
          ...taskConfig.metadata,
          trainingMode,
          interactionMode,
          feedbackMode,
          trainingFeedbackMode: feedbackMode,
          trainingProfile: 'practice',
          replyLanguage: normalizedReplyLanguage,
          reply_language: normalizedReplyLanguage,
          scenario_training: {
            ...scenarioTrainingRecord,
            trainingMode,
            interactionMode,
            feedbackMode,
            replyLanguage: normalizedReplyLanguage,
            reply_language: normalizedReplyLanguage,
          },
        },
      },
    },
    createTrainingSession,
    startRequestData: {
      room_name: `Training: ${scenario.title}`,
      room_type: 'battle_prep',
      runtime_persona: buildScenarioTrainingRuntimePersona(scenario, trainingMode, {
        feedbackMode,
        replyLanguage: normalizedReplyLanguage,
      }),
      opening_message: {
        content: scenario.openingLine,
        metadata: {
          source: 'scenario_training_opening',
          scenarioTrainingId: scenario.id,
          scenarioTitle: scenario.title,
          trainingMode,
          interactionMode,
          feedbackMode,
          trainingFeedbackMode: feedbackMode,
          replyLanguage: normalizedReplyLanguage,
          reply_language: normalizedReplyLanguage,
        },
      },
    },
    startTrainingSession,
    buildTrainingSessionStartRequest: buildRoomBackedTrainingSessionStartRequest,
    trainingMode,
    interactionMode,
    buildChatPath: (roomId, nextTrainingMode, trainingSessionId, nextInteractionMode) => {
      const chatPath = buildTrainingModeChatPath(
        roomId,
        nextTrainingMode,
        trainingSessionId,
        nextInteractionMode,
        {
          trainingFeedbackMode: feedbackMode,
          replyLanguage: normalizedReplyLanguage,
        },
      )
      return `${chatPath}${chatPath.includes('?') ? '&' : '?'}${scenarioParam}`
    },
    buildNavigationState: ({ startedSession }) => ({
      ...buildScenarioTrainingRouteState(scenario, {
        feedbackMode,
        replyLanguage: normalizedReplyLanguage,
      }),
      trainingMode,
      interactionMode,
      trainingFeedbackMode: feedbackMode,
      replyLanguage: normalizedReplyLanguage,
      trainingSessionId: startedSession.session_id,
    }),
    navigate,
    afterStartSession: ({ startedSession }) => {
      const nextProgress = markScenarioTrainingStarted(
        progress,
        scenario.id,
        startedSession.session_id,
        progressScope,
      )
      onProgressChange?.(nextProgress)
      saveScenarioTrainingProgress(nextProgress, progressScope)
    },
  })
}
