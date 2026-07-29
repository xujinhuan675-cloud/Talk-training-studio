import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  ChevronDown,
  CheckCircle2,
  ClipboardCheck,
  Keyboard,
  Languages,
  Loader2,
  Mic2,
  Radio,
  RefreshCw,
  SlidersHorizontal,
  Video,
  Wand2,
} from 'lucide-react'
import TrainingStudioLauncher from '../components/TrainingStudioLauncher'
import { buildRoomBackedTrainingSessionStartRequest, createTrainingSession, startTrainingSession } from '../services/trainingSession'
import { LIVE_COACH_LANGUAGE_OPTIONS, getLiveCoachLanguageLabel } from '../data/liveCoachLanguages'
import { normalizeTrainingReplyLanguage } from '../data/trainingReplyLanguages'
import {
  buildTrainingModeChatPath,
  type InteractionMode,
  type RealtimeVoiceProfile,
  type TrainingFeedbackMode,
  type TrainingMode,
  type TrainingProfile,
} from '../services/trainingMode'
import { launchTrainingSessionFlow } from '../services/trainingLaunch'
import {
  buildTrainingStudioPrompt,
  getDefaultTrainingStudioConfig,
  getExpressionFrameworkLabel,
  getInterviewScenarioPreset,
  getProductScenarioPreset,
  getTrainingDifficultyLabel,
  getTrainingLevelLabel,
  getTrainingScenarioLabel,
  toTrainingRuntimeDifficulty,
  type TrainingStudioConfig,
} from '../services/trainingStudio'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Field, Select, Textarea } from '../components/ui/form'
import { PageHeader } from '../components/ui/page'
import { SegmentedControl } from '../components/ui/segmented-control'
import { Surface } from '../components/ui/surface'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n, type Translate, type TranslationKey } from '../i18n'
import { BattlePrepFlow } from './BattlePrepPage'
import './TrainingStudioPage.css'

type LaunchMode = TrainingMode | 'realtime' | 'live_coach'
type TopLevelMode = TrainingMode | 'live_coach'
type StudioTab = 'training' | 'battle'

const supportsRealtimeVideo = false

const feedbackModeOptions: Array<{
  value: TrainingFeedbackMode
  labelKey: TranslationKey
  descriptionKey: TranslationKey
  instructionKey: TranslationKey
  personaRuleKey: TranslationKey
  trainingPointKey: TranslationKey
  icon: typeof Keyboard
}> = [
  {
    value: 'simulation',
    labelKey: 'training.feedback.simulation.label',
    descriptionKey: 'training.feedback.simulation.desc',
    instructionKey: 'training.feedback.simulation.instruction',
    personaRuleKey: 'training.feedback.simulation.personaRule',
    trainingPointKey: 'training.feedback.simulation.trainingPoint',
    icon: ClipboardCheck,
  },
  {
    value: 'assisted',
    labelKey: 'training.feedback.assisted.label',
    descriptionKey: 'training.feedback.assisted.desc',
    instructionKey: 'training.feedback.assisted.instruction',
    personaRuleKey: 'training.feedback.assisted.personaRule',
    trainingPointKey: 'training.feedback.assisted.trainingPoint',
    icon: CheckCircle2,
  },
  {
    value: 'drill',
    labelKey: 'training.feedback.drill.label',
    descriptionKey: 'training.feedback.drill.desc',
    instructionKey: 'training.feedback.drill.instruction',
    personaRuleKey: 'training.feedback.drill.personaRule',
    trainingPointKey: 'training.feedback.drill.trainingPoint',
    icon: RefreshCw,
  },
]

interface TrainingStudioPageProps {
  initialProfile?: TrainingProfile
}

function getRouteStateObject(state: unknown): Record<string, unknown> {
  return state && typeof state === 'object' ? state as Record<string, unknown> : {}
}

function getRouteTrainingStudioConfig(state: unknown): TrainingStudioConfig | null {
  const value = getRouteStateObject(state).trainingStudioConfig
  return value && typeof value === 'object' ? value as TrainingStudioConfig : null
}

function getRouteLaunchMode(state: unknown): LaunchMode | null {
  const value = getRouteStateObject(state).trainingStudioMode
  return typeof value === 'string' && ['text', 'voice', 'video', 'realtime', 'live_coach'].includes(value)
    ? value as LaunchMode
    : null
}

function getRouteFeedbackMode(state: unknown): TrainingFeedbackMode | null {
  const value = getRouteStateObject(state).trainingFeedbackMode
  return typeof value === 'string' && ['simulation', 'assisted', 'drill'].includes(value)
    ? value as TrainingFeedbackMode
    : null
}

function getRouteStringValue(state: unknown, key: string): string | null {
  const value = getRouteStateObject(state)[key]
  return typeof value === 'string' ? value : null
}

const modeOptions: Array<{
  value: TopLevelMode
  defaultMode: LaunchMode
  labelKey: TranslationKey
  descriptionKey: TranslationKey
  icon: typeof Keyboard
  interactions?: Array<{
    id: string
    value?: LaunchMode
    labelKey: TranslationKey
    descriptionKey: TranslationKey
    icon: typeof Keyboard
    disabled?: boolean
    badgeKey?: TranslationKey
  }>
}> = [
  {
    value: 'text',
    defaultMode: 'text',
    labelKey: 'training.mode.text.label',
    descriptionKey: 'training.mode.text.desc',
    icon: Keyboard,
  },
  {
    value: 'voice',
    defaultMode: 'voice',
    labelKey: 'training.mode.voice.label',
    descriptionKey: 'training.mode.voice.desc',
    icon: Mic2,
    interactions: [
      {
        id: 'voice-turn-based',
        value: 'voice',
        labelKey: 'training.interaction.turnBased.label',
        descriptionKey: 'training.interaction.voice.turnBased.desc',
        icon: Mic2,
      },
      {
        id: 'voice-realtime',
        value: 'realtime',
        labelKey: 'training.interaction.realtime.label',
        descriptionKey: 'training.interaction.voice.realtime.desc',
        icon: Radio,
      },
    ],
  },
  {
    value: 'video',
    defaultMode: 'video',
    labelKey: 'training.mode.video.label',
    descriptionKey: 'training.mode.video.desc',
    icon: Video,
    interactions: [
      {
        id: 'video-turn-based',
        value: 'video',
        labelKey: 'training.interaction.turnBased.label',
        descriptionKey: 'training.interaction.video.turnBased.desc',
        icon: Video,
      },
      {
        id: 'video-realtime',
        labelKey: 'training.interaction.realtime.label',
        descriptionKey: 'training.interaction.video.realtime.desc',
        icon: Radio,
        disabled: !supportsRealtimeVideo,
        badgeKey: 'training.interaction.comingSoon',
      },
    ],
  },
  {
    value: 'live_coach',
    defaultMode: 'live_coach',
    labelKey: 'training.mode.liveCoach.label',
    descriptionKey: 'training.mode.liveCoach.desc',
    icon: Languages,
  },
]

const modeLabelKeys: Record<LaunchMode, TranslationKey> = {
  text: 'training.mode.text.label',
  voice: 'training.mode.voice.label',
  video: 'training.mode.video.label',
  realtime: 'training.mode.realtime.label',
  live_coach: 'training.mode.liveCoach.label',
}

function getModeLabel(mode: LaunchMode, t: Translate): string {
  return t(modeLabelKeys[mode])
}

function modeInstruction(mode: LaunchMode, t: Translate): string {
  if (mode === 'voice') {
    return t('training.mode.voice.instruction')
  }
  if (mode === 'video') {
    return t('training.mode.video.instruction')
  }
  if (mode === 'realtime') {
    return t('training.mode.realtime.instruction')
  }
  if (mode === 'live_coach') {
    return t('training.mode.liveCoach.instruction')
  }
  return t('training.mode.text.instruction')
}

function getFeedbackModeOption(mode: TrainingFeedbackMode) {
  return feedbackModeOptions.find((option) => option.value === mode) ?? feedbackModeOptions[0]
}

function getFeedbackModeLabel(mode: TrainingFeedbackMode, t: Translate): string {
  return t(getFeedbackModeOption(mode).labelKey)
}

function feedbackModeInstruction(mode: TrainingFeedbackMode, t: Translate): string {
  return t(getFeedbackModeOption(mode).instructionKey)
}

function getLaunchTrainingMode(mode: LaunchMode): TrainingMode {
  return mode === 'realtime' || mode === 'live_coach' ? 'voice' : mode
}

function getLaunchInteractionMode(mode: LaunchMode): InteractionMode {
  return mode === 'realtime' || mode === 'live_coach' ? 'realtime' : 'turn_based'
}

function isModeCardSelected(cardMode: TopLevelMode, selectedMode: LaunchMode): boolean {
  return cardMode === selectedMode
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function splitTechStack(value: string, fallback: string): string[] {
  const items = value
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
  return items.length > 0 ? items : [fallback]
}

export default function TrainingStudioPage({ initialProfile = 'practice' }: TrainingStudioPageProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { locale, t, tr } = useI18n()
  const { requireAuthenticated } = useAuthContext()
  const routeState = location.state
  const routeConfig = getRouteTrainingStudioConfig(routeState)
  const routeMode = getRouteLaunchMode(routeState)
  const routeFeedbackMode = getRouteFeedbackMode(routeState)
  const [config, setConfig] = useState<TrainingStudioConfig>(() => routeConfig ?? getDefaultTrainingStudioConfig(t))
  const previousDefaultsRef = useRef(getDefaultTrainingStudioConfig(t))
  const [mode, setMode] = useState<LaunchMode>(() => initialProfile === 'live_coach' ? 'live_coach' : routeMode ?? 'voice')
  const [feedbackMode, setFeedbackMode] = useState<TrainingFeedbackMode>(() => routeFeedbackMode ?? 'simulation')
  const [activeTab, setActiveTab] = useState<StudioTab>('training')
  const [battlePrepStep, setBattlePrepStep] = useState<1 | 2>(1)
  const [parametersOpen, setParametersOpen] = useState(false)
  const [liveCoachSourceLanguage, setLiveCoachSourceLanguage] = useState(() => getRouteStringValue(routeState, 'liveCoachSourceLanguage') ?? 'zh-CN')
  const [liveCoachTargetLanguage, setLiveCoachTargetLanguage] = useState(() => getRouteStringValue(routeState, 'liveCoachTargetLanguage') ?? 'en-US')
  const [goal, setGoal] = useState(() => getRouteStringValue(routeState, 'trainingGoal') ?? '')
  const [starting, setStarting] = useState<'quick' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const effectiveFeedbackMode = mode === 'live_coach' ? 'assisted' : feedbackMode

  useEffect(() => {
    if (initialProfile === 'live_coach') {
      setMode('live_coach')
    }
  }, [initialProfile])

  useEffect(() => {
    const previousDefaults = previousDefaultsRef.current
    const nextDefaults = getDefaultTrainingStudioConfig(t)

    setConfig((current) => ({
      ...current,
      role: current.role === previousDefaults.role ? nextDefaults.role : current.role,
      techStack: current.techStack === previousDefaults.techStack ? nextDefaults.techStack : current.techStack,
    }))
    previousDefaultsRef.current = nextDefaults
  }, [t])

  const prompt = useMemo(() => {
    const scenario = getTrainingScenarioLabel(config.scenario, t)
    const role = config.role.trim() || t('training.defaults.roleFallback')
    const base = goal.trim() || t('training.prompt.defaultGoal', { role, scenario })
    return buildTrainingStudioPrompt(
      config,
      `${base}\n\n${modeInstruction(mode, t)}\n${feedbackModeInstruction(effectiveFeedbackMode, t)}`,
      t,
    )
  }, [config, effectiveFeedbackMode, goal, mode, t])

  const trainingConfigSummary = useMemo(() => {
    const scenario = getTrainingScenarioLabel(config.scenario, t)
    const difficulty = getTrainingDifficultyLabel(config.difficulty, t)
    const framework = getExpressionFrameworkLabel(config.framework, t)
    return tr(
      '{scenario} · {difficulty} · {framework} · {count} 题',
      '{scenario} · {difficulty} · {framework} · {count} questions',
      {
        count: config.questionCount,
        difficulty,
        framework,
        scenario,
      },
    )
  }, [config.difficulty, config.framework, config.questionCount, config.scenario, t, tr])
  const selectedModeLabel = getModeLabel(mode, t)
  const selectedFeedbackModeLabel = getFeedbackModeLabel(effectiveFeedbackMode, t)

  const startQuickSession = async () => {
    if (!requireAuthenticated()) return
    setStarting('quick')
    setError(null)
    try {
      const role = config.role.trim() || t('training.defaults.roleFallback')
      const scenario = getTrainingScenarioLabel(config.scenario, t)
      const difficulty = getTrainingDifficultyLabel(config.difficulty, t)
      const framework = getExpressionFrameworkLabel(config.framework, t)
      const level = getTrainingLevelLabel(config.level, t)
      const trainingMode = getLaunchTrainingMode(mode)
      const interactionMode = getLaunchInteractionMode(mode)
      const realtimeProfile: RealtimeVoiceProfile | null = mode === 'realtime' ? 'speech_to_speech' : null
      const modeLabel = getModeLabel(mode, t)
      const feedbackModeLabel = getFeedbackModeLabel(effectiveFeedbackMode, t)
      const feedbackOption = getFeedbackModeOption(effectiveFeedbackMode)
      const trainingProfile: TrainingProfile = mode === 'live_coach' ? 'live_coach' : 'practice'
      const isLiveCoachMode = trainingProfile === 'live_coach'
      const replyLanguage = normalizeTrainingReplyLanguage(config.replyLanguage)
      const sourceLanguageLabel = getLiveCoachLanguageLabel(liveCoachSourceLanguage, locale)
      const targetLanguageLabel = getLiveCoachLanguageLabel(liveCoachTargetLanguage, locale)
      const interviewScenarioPreset = getInterviewScenarioPreset(config.interviewScenarioPreset)
      const productScenarioPreset = getProductScenarioPreset(config.productScenarioPreset)
      const interviewStakeholder = config.scenario === 'interview' ? interviewScenarioPreset : undefined
      const productStakeholder = config.scenario === 'product_management' ? productScenarioPreset : undefined
      const scenarioStakeholder = interviewStakeholder ?? productStakeholder
      const runtimePersonaName = isLiveCoachMode
        ? t('training.liveCoach.personaName')
        : scenarioStakeholder
          ? t(scenarioStakeholder.personaNameKey)
          : t('training.prompt.personaName', { role })
      const runtimePersonaRole = isLiveCoachMode
        ? t('training.liveCoach.personaRole')
        : scenarioStakeholder
          ? t(scenarioStakeholder.personaRoleKey)
          : t('training.prompt.personaRole', { level, scenario })
      const runtimePersonaStyle = isLiveCoachMode
        ? t('training.liveCoach.personaStyle')
        : scenarioStakeholder
          ? `${t(scenarioStakeholder.personaStyleKey, { difficulty, framework, mode: modeLabel })}\n${t(feedbackOption.personaRuleKey)}`
          : `${t('training.prompt.personaStyle', { difficulty, framework, mode: modeLabel })}\n${t(feedbackOption.personaRuleKey)}`
      const runtimeScenarioContext = isLiveCoachMode
        ? `${prompt}\n\n${t('training.liveCoach.languageContext', {
            sourceLanguage: sourceLanguageLabel,
            targetLanguage: targetLanguageLabel,
          })}`
        : prompt
      const runtimeTrainingPoints = isLiveCoachMode
        ? [
            t('training.liveCoach.nextReplyPoint'),
            t('training.liveCoach.riskPoint'),
            t('training.liveCoach.translationPoint'),
            t('training.liveCoach.reviewPoint'),
          ]
        : [
            t('training.prompt.structurePoint', { framework }),
            ...(interviewStakeholder
              ? [
                  t('training.prompt.interviewEvidencePoint'),
                  t('training.prompt.interviewFollowupPoint'),
                ]
              : []),
            ...(productStakeholder
              ? [
                  t('training.prompt.productAlignmentPoint'),
                  t('training.prompt.productTradeoffPoint'),
                ]
              : []),
            t(feedbackOption.trainingPointKey),
            t('training.prompt.deliveryPoint', { mode: modeLabel }),
            t('training.prompt.evidencePoint'),
          ]
      await launchTrainingSessionFlow({
        createTrainingSessionRequest: {
          mode: trainingMode,
          task_config: {
            role,
            level,
            tech_stack: splitTechStack(config.techStack, scenario),
            question_type_ratios: { ...config.questionMix },
            question_count: config.questionCount,
            framework: config.framework,
            difficulty: config.difficulty,
            category: config.scenario,
            metadata: {
              source: isLiveCoachMode ? 'live_coach_mvp' : 'training_studio',
              trainingMode,
              interactionMode,
              ...(realtimeProfile ? { realtimeProfile } : {}),
              trainingProfile,
              feedbackMode: effectiveFeedbackMode,
              trainingFeedbackMode: effectiveFeedbackMode,
              replyLanguage,
              reply_language: replyLanguage,
              feedbackPolicy: {
                mode: effectiveFeedbackMode,
                version: 1,
                channelAgnostic: true,
              },
              ...(isLiveCoachMode
                ? {
                    liveCoach: {
                      sourceLanguage: liveCoachSourceLanguage,
                      targetLanguage: liveCoachTargetLanguage,
                      captureStrategy: 'browser_microphone_mvp',
                      transcriptStrategy: 'chat_room_messages',
                      translationStrategy: 'text_first_mvp',
                      extensionPoints: [
                        'system_audio_tap',
                        'virtual_microphone',
                        'speech_to_speech_translation',
                        'prosody_preservation',
                        '70_plus_languages',
                      ],
                    },
                  }
                : {}),
            },
          },
        },
        createTrainingSession,
        startRequestData: {
          room_name: `Training: ${runtimePersonaName}`,
          room_type: 'battle_prep',
          runtime_persona: {
            name: runtimePersonaName,
            role: runtimePersonaRole,
            style: runtimePersonaStyle,
            scenario_context: runtimeScenarioContext,
            training_points: runtimeTrainingPoints,
            difficulty: toTrainingRuntimeDifficulty(config.difficulty),
          },
        },
        startTrainingSession,
        buildTrainingSessionStartRequest: buildRoomBackedTrainingSessionStartRequest,
        trainingMode,
        interactionMode,
        buildChatPath: (roomId, nextTrainingMode, trainingSessionId, nextInteractionMode) => buildTrainingModeChatPath(
          roomId,
          nextTrainingMode,
          trainingSessionId,
          nextInteractionMode,
          {
            trainingProfile,
            realtimeProfile,
            trainingFeedbackMode: effectiveFeedbackMode,
            replyLanguage,
            sourceLanguage: isLiveCoachMode ? liveCoachSourceLanguage : null,
            targetLanguage: isLiveCoachMode ? liveCoachTargetLanguage : null,
          },
        ),
        buildNavigationState: ({ startedSession }) => ({
          source: isLiveCoachMode ? 'live-coach' : 'training-studio',
          trainingMode,
          interactionMode,
          trainingSessionId: startedSession.session_id,
          ...(realtimeProfile ? { realtimeProfile } : {}),
          trainingProfile,
          trainingFeedbackMode: effectiveFeedbackMode,
          feedbackMode: effectiveFeedbackMode,
          feedbackModeLabel,
          replyLanguage,
          sourceLanguage: isLiveCoachMode ? liveCoachSourceLanguage : undefined,
          targetLanguage: isLiveCoachMode ? liveCoachTargetLanguage : undefined,
        }),
        navigate,
      })
    } catch (e: unknown) {
      setError(getErrorMessage(e, t('training.error.startFailed')))
      setStarting(null)
    }
  }

  return (
    <div className="training-studio-page" data-workbench-skin="training">
      <div className="training-studio-shell">
        <PageHeader
          className="training-studio-header"
          title={t('training.page.title')}
          description={t('training.page.subtitle')}
        />

        <Surface
          as="section"
          className="training-studio-tabs-panel"
          padding="md"
          aria-label={tr('训练工作台页面', 'Training studio pages')}
        >
          <SegmentedControl
            ariaLabel={tr('训练工作台页面', 'Training studio pages')}
            className="training-studio-page-tabs"
            onValueChange={setActiveTab}
            options={[
              {
                value: 'training',
                ariaLabel: t('training.launch.quickStart'),
                label: t('training.launch.quickStart'),
                disabled: starting !== null,
              },
              {
                value: 'battle',
                ariaLabel: t('training.launch.prepareFirst'),
                label: t('training.launch.prepareFirst'),
                disabled: starting !== null,
              },
            ]}
            size="sm"
            value={activeTab}
          />

          {activeTab === 'training' && (
            <div className="training-studio-start-steps" aria-label={tr('快速开始流程', 'Quick start steps')}>
              <div className="training-studio-start-step">
                <span className="training-studio-start-step-dot done">1</span>
                <span className="training-studio-start-step-label">{tr('选择模式', 'Choose mode')}</span>
              </div>
              <div className="training-studio-start-step-line done" />
              <div className="training-studio-start-step">
                <span className="training-studio-start-step-dot done">2</span>
                <span className="training-studio-start-step-label">{tr('选择练法', 'Choose practice')}</span>
              </div>
              <div className="training-studio-start-step-line done" />
              <div className="training-studio-start-step">
                <span className="training-studio-start-step-dot active">3</span>
                <span className="training-studio-start-step-label active">{t('common.startTraining')}</span>
              </div>
            </div>
          )}
          {activeTab === 'battle' && (
            <div className="training-studio-start-steps" aria-label={tr('准备流程', 'Preparation steps')}>
              {[1, 2].map((stepNumber) => (
                <div key={stepNumber} className="training-studio-start-step">
                  <span
                    className={`training-studio-start-step-dot ${
                      battlePrepStep === stepNumber ? 'active' : battlePrepStep > stepNumber ? 'done' : ''
                    }`}
                  >
                    {stepNumber}
                  </span>
                  <span className={`training-studio-start-step-label${battlePrepStep === stepNumber ? ' active' : ''}`}>
                    {stepNumber === 1
                      ? tr('描述会议', 'Describe Meeting')
                      : tr('确认对手', 'Confirm opponent')}
                  </span>
                  {stepNumber < 2 && (
                    <div className={`training-studio-start-step-line${battlePrepStep > stepNumber ? ' done' : ''}`} />
                  )}
                </div>
              ))}
            </div>
          )}
        </Surface>

        {activeTab === 'training' ? (
          <section className="training-studio-training-panel" aria-label={t('training.launch.quickStart')}>
            <div className="training-studio-training-actions">
              <div className="training-studio-training-action-copy">
                <h2>{t('training.launch.quickStart')}</h2>
                <p>{selectedModeLabel} · {selectedFeedbackModeLabel} · {trainingConfigSummary}</p>
              </div>
              <div className="training-studio-action-stack">
                <Button
                  className="training-studio-action"
                  variant="primary"
                  onClick={startQuickSession}
                  disabled={starting !== null}
                >
                  {starting === 'quick' ? <Loader2 size={16} className="training-studio-spin" /> : <Wand2 size={16} />}
                  {t('common.startTraining')}
                </Button>
                <Button
                  className="training-studio-parameters-toggle"
                  variant="secondary"
                  size="sm"
                  onClick={() => setParametersOpen((open) => !open)}
                  disabled={starting !== null}
                  aria-expanded={parametersOpen}
                  aria-controls="training-studio-parameters-panel"
                >
                  <SlidersHorizontal size={14} />
                  {parametersOpen ? tr('收起训练参数', 'Hide training parameters') : tr('调整训练参数', 'Adjust training parameters')}
                  <ChevronDown
                    aria-hidden="true"
                    className={`training-studio-parameters-toggle-chevron${parametersOpen ? ' open' : ''}`}
                    size={14}
                  />
                </Button>
              </div>
            </div>

            {parametersOpen && (
              <section
                id="training-studio-parameters-panel"
                className="training-studio-parameters-panel"
                aria-label={t('training.launch.summaryTitle')}
              >
                <div className="training-studio-config-inline">
                  <TrainingStudioLauncher value={config} onChange={setConfig} disabled={starting !== null} />
                </div>
              </section>
            )}

            {error && (
              <div className="training-studio-error" role="alert">
                {error}
              </div>
            )}

            <section className="training-studio-mode-panel" aria-label={t('training.page.responseModeAria')}>
          {modeOptions.map((item) => {
            const Icon = item.icon
            const selected = isModeCardSelected(item.value, mode)
            return (
              <div
                key={item.value}
                className={`training-studio-mode ${selected ? 'selected' : ''}`}
              >
                <Button
                  className="training-studio-mode-main"
                  variant="ghost"
                  onClick={() => setMode(item.defaultMode)}
                  disabled={starting !== null}
                  aria-pressed={selected}
                >
                  <Icon size={20} />
                  <span>{t(item.labelKey)}</span>
                  <small>{t(item.descriptionKey)}</small>
                </Button>
                {item.interactions && (
                  <div
                    className="training-studio-interaction-options"
                    role="group"
                    aria-label={`${t(item.labelKey)} ${t('training.page.interactionOptionsAria')}`}
                  >
                    {item.interactions.map((option) => {
                      const OptionIcon = option.icon
                      const optionSelected = option.value === mode
                      const disabled = starting !== null || option.disabled || !option.value
                      return (
                        <Button
                          key={option.id}
                          className={`training-studio-interaction ${optionSelected ? 'selected' : ''}`}
                          variant="ghost"
                          onClick={() => {
                            if (option.value) {
                              setMode(option.value)
                            }
                          }}
                          disabled={disabled}
                          aria-pressed={optionSelected}
                        >
                          <span className="training-studio-interaction-label">
                            <OptionIcon size={14} />
                            {t(option.labelKey)}
                            {option.badgeKey && (
                              <Badge tone="neutral" className="training-studio-interaction-badge">
                                {t(option.badgeKey)}
                              </Badge>
                            )}
                          </span>
                          <small>{t(option.descriptionKey)}</small>
                        </Button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </section>

        <section className="training-studio-feedback-panel" aria-label={t('training.feedback.aria')}>
          <div className="training-studio-panel-head">
            <div>
              <h2>{t('training.feedback.title')}</h2>
              <p>{t('training.feedback.subtitle')}</p>
            </div>
            {mode === 'live_coach' && (
              <Badge tone="neutral">{t('training.feedback.liveCoachLock')}</Badge>
            )}
          </div>
          <SegmentedControl
            ariaLabel={t('training.feedback.aria')}
            className="training-studio-feedback-options"
            onValueChange={setFeedbackMode}
            options={feedbackModeOptions.map((item) => {
              const Icon = item.icon
              return {
                value: item.value,
                ariaLabel: `${t(item.labelKey)}. ${t(item.descriptionKey)}`,
                title: t(item.descriptionKey),
                label: (
                  <>
                    <span>
                      <Icon size={15} />
                      {t(item.labelKey)}
                    </span>
                    <small>{t(item.descriptionKey)}</small>
                  </>
                ),
                disabled: starting !== null || mode === 'live_coach',
              }
            })}
            value={effectiveFeedbackMode}
          />
        </section>

        <div className="training-studio-grid">
          <div className="training-studio-main">
            <Field className="training-studio-goal" label={t('training.goal.label')}>
              <Textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={4}
                placeholder={t('training.goal.placeholder')}
                disabled={starting !== null}
              />
            </Field>

            {mode === 'live_coach' && (
              <section className="training-studio-live-coach-panel" aria-label={t('training.liveCoach.panelAria')}>
                <Field label={t('training.liveCoach.sourceLanguage')}>
                  <Select
                    value={liveCoachSourceLanguage}
                    onChange={(event) => setLiveCoachSourceLanguage(event.target.value)}
                    disabled={starting !== null}
                  >
                    {LIVE_COACH_LANGUAGE_OPTIONS.map((option) => (
                      <option key={option.code} value={option.code}>
                        {getLiveCoachLanguageLabel(option.code, locale)}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label={t('training.liveCoach.targetLanguage')}>
                  <Select
                    value={liveCoachTargetLanguage}
                    onChange={(event) => setLiveCoachTargetLanguage(event.target.value)}
                    disabled={starting !== null}
                  >
                    {LIVE_COACH_LANGUAGE_OPTIONS.map((option) => (
                      <option key={option.code} value={option.code}>
                        {getLiveCoachLanguageLabel(option.code, locale)}
                      </option>
                    ))}
                  </Select>
                </Field>
                <div className="training-studio-live-coach-badge">
                  <Languages size={14} />
                  {t('training.liveCoach.languageAdapter')}
                </div>
              </section>
            )}
          </div>
        </div>

          </section>
        ) : (
          <div className="training-studio-battle-panel">
            <BattlePrepFlow
              embedded
              onStepChange={setBattlePrepStep}
              onStudioConfigChange={setConfig}
              showSteps={false}
              studioConfig={config}
            />
          </div>
        )}
      </div>
    </div>
  )
}
