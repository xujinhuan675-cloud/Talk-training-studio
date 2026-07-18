import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  Keyboard,
  Languages,
  Loader2,
  Mic2,
  Radio,
  RefreshCw,
  ShieldCheck,
  Video,
  Wand2,
  XCircle,
} from 'lucide-react'
import TrainingStudioLauncher from '../components/TrainingStudioLauncher'
import { startBattle } from '../services/api'
import { createTrainingSession, startTrainingSession } from '../services/trainingSession'
import { LIVE_COACH_LANGUAGE_OPTIONS, getLiveCoachLanguageLabel } from '../data/liveCoachLanguages'
import {
  buildTrainingModeChatPath,
  type InteractionMode,
  type TrainingMode,
  type TrainingProfile,
} from '../services/trainingMode'
import {
  buildTrainingStudioPrompt,
  buildTrainingStudioCapabilityReadiness,
  getDefaultTrainingStudioConfig,
  getExpressionFrameworkLabel,
  getInterviewScenarioPreset,
  getProductScenarioPreset,
  getTrainingDifficultyLabel,
  getTrainingLevelLabel,
  getTrainingScenarioLabel,
  toBattleDifficulty,
  fetchRealtimeCapabilities,
  type RealtimeCapabilities,
  type RealtimeReadinessIssue,
  type RuntimeCapabilityRegistry,
  type TrainingStudioCapabilityItem,
  type TrainingStudioConfig,
  type TrainingStudioReadinessStatus,
} from '../services/trainingStudio'
import {
  fetchLlmRegistry,
  getLlmRegistryModelChoices,
  type LLMProviderMetadata,
} from '../services/llmRegistry'
import { useI18n, type Translate, type TranslateInline, type TranslationKey } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { buildTrainingSessionStartRequest } from '../services/trainingSession'
import './TrainingStudioPage.css'

type LaunchMode = TrainingMode | 'realtime' | 'live_coach'
type TopLevelMode = TrainingMode | 'live_coach'

const supportsRealtimeVideo = false

interface TrainingStudioPageProps {
  initialProfile?: TrainingProfile
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

function getLaunchTrainingMode(mode: LaunchMode): TrainingMode {
  return mode === 'realtime' || mode === 'live_coach' ? 'voice' : mode
}

function getLaunchInteractionMode(mode: LaunchMode): InteractionMode {
  return mode === 'realtime' || mode === 'live_coach' ? 'realtime' : 'turn_based'
}

function isModeCardSelected(cardMode: TopLevelMode, selectedMode: LaunchMode): boolean {
  if (cardMode === 'voice') {
    return selectedMode === 'voice' || selectedMode === 'realtime'
  }
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

type RealtimeDiagnosticTone = 'ready' | 'warning' | 'blocked' | 'loading'

interface RealtimeDiagnosticStatus {
  label: string
  tone: RealtimeDiagnosticTone
}

function sanitizeRealtimeDiagnosticText(value: string): string {
  return value
    .replace(/sk-[A-Za-z0-9_-]{6,}/g, 'sk-***')
    .replace(/\b(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}/gi, '$1 ***')
    .replace(/\b(api[_-]?key|authorization|token)(\s*[:=]\s*)([^,\s;]+)/gi, '$1$2***')
}

function cleanDiagnosticText(value: unknown): string | null {
  if (value === undefined || value === null) return null
  if (typeof value === 'object' || typeof value === 'function' || typeof value === 'symbol') return null
  const text = String(value).trim()
  return text ? sanitizeRealtimeDiagnosticText(text) : null
}

function formatBooleanStatus(value: boolean, tr: TranslateInline): string {
  return value ? tr('是', 'Yes') : tr('否', 'No')
}

function getOpenAIRealtimeStatus(
  capabilities: RealtimeCapabilities['openaiRealtime'],
  tr: TranslateInline,
): RealtimeDiagnosticStatus {
  if (capabilities.readyForCall) {
    return { label: tr('可发起通话', 'Ready for call'), tone: 'ready' }
  }
  if (capabilities.readiness?.status) {
    return { label: sanitizeRealtimeDiagnosticText(capabilities.readiness.status), tone: 'blocked' }
  }
  if (!capabilities.effectiveKey) {
    return { label: tr('缺少 Key', 'Missing key'), tone: 'blocked' }
  }
  if (!capabilities.configured) {
    return { label: tr('配置不完整', 'Incomplete'), tone: 'warning' }
  }
  return { label: tr('已就绪', 'Ready'), tone: 'ready' }
}

function getPipecatRealtimeStatus(
  capabilities: RealtimeCapabilities['pipecat'],
  tr: TranslateInline,
): RealtimeDiagnosticStatus {
  if (capabilities.readyForCall) {
    return { label: tr('可发起通话', 'Ready for call'), tone: 'ready' }
  }
  if (capabilities.readiness?.status) {
    return { label: sanitizeRealtimeDiagnosticText(capabilities.readiness.status), tone: 'blocked' }
  }
  if (capabilities.available) {
    return { label: tr('需处理阻塞项', 'Blocked'), tone: 'warning' }
  }
  return { label: tr('不可用', 'Unavailable'), tone: 'blocked' }
}

function realtimeStatusIcon(tone: RealtimeDiagnosticTone) {
  if (tone === 'ready') return <CheckCircle2 size={14} />
  if (tone === 'loading') return <Loader2 size={14} className="training-studio-spin" />
  if (tone === 'warning') return <AlertTriangle size={14} />
  return <XCircle size={14} />
}

function capabilityStatusIcon(status: TrainingStudioReadinessStatus, loading = false) {
  if (loading && status === 'unknown') return <Loader2 size={14} className="training-studio-spin" />
  if (status === 'ready') return <CheckCircle2 size={14} />
  if (status === 'blocked') return <XCircle size={14} />
  return <AlertTriangle size={14} />
}

function capabilityStatusLabel(status: TrainingStudioReadinessStatus, tr: TranslateInline): string {
  if (status === 'ready') return tr('Ready', 'Ready')
  if (status === 'warning') return tr('Needs attention', 'Needs attention')
  if (status === 'blocked') return tr('Blocked', 'Blocked')
  return tr('Not loaded', 'Not loaded')
}

function compactCapabilityTag(value: string): string {
  const text = value.replace(/\s+/g, ' ').trim()
  if (text.length <= 42) return text
  return `${text.slice(0, 39)}...`
}

function formatRealtimeFeatureLabel(feature: string, tr: TranslateInline): string {
  const normalized = feature.split(':')[0]?.trim().toLowerCase()
  if (normalized === 'stt') return tr('STT 语音识别', 'STT transcription')
  if (normalized === 'tts') return tr('TTS 语音合成', 'TTS synthesis')
  if (normalized === 'llm') return tr('LLM 文本模型', 'LLM model')
  if (normalized === 'vad') return tr('VAD 语音活动检测', 'VAD voice activity')
  if (normalized === 'turndetection') return tr('turnDetection 轮次检测', 'turnDetection')
  if (normalized === 'websocket') return tr('WebSocket 传输', 'WebSocket transport')
  if (normalized === 'core') return tr('Pipecat 核心模块', 'Pipecat core')
  return sanitizeRealtimeDiagnosticText(feature)
}

function issueSignature(issue: RealtimeReadinessIssue): string {
  return [
    issue.code,
    issue.phase,
    issue.feature,
    issue.message,
    issue.modules?.join('|'),
    issue.missingEnv?.join('|'),
  ].filter(Boolean).join('::')
}

function mergeRealtimeIssues(
  blockingReasons: RealtimeReadinessIssue[] | undefined,
  errors: RealtimeReadinessIssue[] | undefined,
): RealtimeReadinessIssue[] {
  const result: RealtimeReadinessIssue[] = []
  const seen = new Set<string>()
  for (const issue of [...(blockingReasons ?? []), ...(errors ?? [])]) {
    const signature = issueSignature(issue)
    if (seen.has(signature)) continue
    seen.add(signature)
    result.push(issue)
  }
  return result
}

function formatRealtimeIssueTitle(issue: RealtimeReadinessIssue, tr: TranslateInline): string {
  if (issue.code === 'MISSING_OPENAI_API_KEY') return tr('缺少 OpenAI Realtime Key', 'Missing OpenAI Realtime key')
  if (issue.code === 'MISSING_OPENAI_REALTIME_MODEL') return tr('缺少 OpenAI Realtime 模型', 'Missing OpenAI Realtime model')
  if (issue.code === 'MISSING_OPENAI_REALTIME_VOICE') return tr('缺少 OpenAI Realtime 声音', 'Missing OpenAI Realtime voice')
  if (issue.code === 'PIPECAT_MODULE_UNAVAILABLE') return tr('Pipecat 模块缺失', 'Pipecat module unavailable')
  if (issue.code === 'PIPECAT_WEBSOCKET_UNAVAILABLE') return tr('Pipecat WebSocket 不可用', 'Pipecat WebSocket unavailable')
  if (issue.code === 'PIPECAT_FEATURE_UNAVAILABLE') {
    const feature = issue.feature ? `: ${formatRealtimeFeatureLabel(issue.feature, tr)}` : ''
    return `${tr('Pipecat 能力缺失', 'Pipecat feature unavailable')}${feature}`
  }
  if (issue.code === 'PIPECAT_CAPABILITY_ERROR') return tr('Pipecat 能力检查失败', 'Pipecat capability check failed')
  return sanitizeRealtimeDiagnosticText(issue.code || issue.message || tr('未知阻塞项', 'Unknown blocker'))
}

function formatRealtimeIssueDetail(issue: RealtimeReadinessIssue, tr: TranslateInline): string {
  const message = cleanDiagnosticText(issue.message)
  if (message) return message
  if (issue.modules && issue.modules.length > 0) {
    return tr('缺少模块：{modules}', 'Missing modules: {modules}', { modules: issue.modules.join(', ') })
  }
  if (issue.missingEnv && issue.missingEnv.length > 0) {
    return tr('缺少环境变量：{env}', 'Missing env vars: {env}', { env: issue.missingEnv.join(', ') })
  }
  return tr('后端未返回更多细节。', 'No additional detail returned by the backend.')
}

function addUniqueHint(target: string[], hint: string): void {
  if (!target.includes(hint)) target.push(hint)
}

function buildRealtimeReadinessHints(
  capabilities: RealtimeCapabilities,
  tr: TranslateInline,
): string[] {
  const hints: string[] = []
  const openai = capabilities.openaiRealtime
  const pipecat = capabilities.pipecat

  if (!openai.effectiveKey) {
    addUniqueHint(
      hints,
      tr(
        '缺少 OpenAI Realtime Key：配置 REALTIME_OPENAI_API_KEY、LLM__API_KEY 或 OPENAI_API_KEY 后重启后端。',
        'Missing OpenAI Realtime key: set REALTIME_OPENAI_API_KEY, LLM__API_KEY, or OPENAI_API_KEY, then restart the backend.',
      ),
    )
  } else if (!openai.configured) {
    addUniqueHint(
      hints,
      tr(
        'OpenAI Realtime 配置不完整：确认 realtime model 与 voice 都已配置。',
        'OpenAI Realtime is incomplete: confirm both realtime model and voice are configured.',
      ),
    )
  }

  if (!pipecat.coreAvailable) {
    addUniqueHint(
      hints,
      tr(
        'Pipecat 核心模块不可用：检查 backend 依赖是否安装了 pipecat-ai voice 相关 extras。',
        'Pipecat core modules are unavailable: check that backend dependencies include the pipecat-ai voice extras.',
      ),
    )
  }
  if (!pipecat.websocketAvailable) {
    addUniqueHint(
      hints,
      tr(
        'Pipecat WebSocket 传输不可用：实时通话需要 websocket transport 模块。',
        'Pipecat WebSocket transport is unavailable: realtime calls require the websocket transport module.',
      ),
    )
  }

  const featureHints: Array<[boolean, string]> = [
    [
      pipecat.sttAvailable,
      tr('缺少 STT：Pipecat 需要可用的 OpenAI STT/transcription 服务。', 'Missing STT: Pipecat needs an available OpenAI STT/transcription service.'),
    ],
    [
      pipecat.ttsAvailable,
      tr('缺少 TTS：Pipecat 需要可用的 OpenAI TTS/voice 输出服务。', 'Missing TTS: Pipecat needs an available OpenAI TTS/voice output service.'),
    ],
    [
      pipecat.llmAvailable,
      tr('缺少 LLM：Pipecat 需要可用的 OpenAI LLM 服务。', 'Missing LLM: Pipecat needs an available OpenAI LLM service.'),
    ],
    [
      pipecat.vadAvailable,
      tr('缺少 VAD：安装或启用 Silero VAD 相关依赖。', 'Missing VAD: install or enable the Silero VAD dependencies.'),
    ],
    [
      pipecat.turnDetectionAvailable,
      tr('缺少 turnDetection：Pipecat 用户轮次检测入口不可用。', 'Missing turnDetection: the Pipecat user-turn detection entrypoint is unavailable.'),
    ],
  ]

  for (const [available, hint] of featureHints) {
    if (!available) addUniqueHint(hints, hint)
  }

  if (pipecat.missingModules.length > 0) {
    addUniqueHint(
      hints,
      tr('缺少模块：{modules}', 'Missing modules: {modules}', { modules: pipecat.missingModules.join(', ') }),
    )
  }
  if (pipecat.optionalMissingModules.length > 0) {
    addUniqueHint(
      hints,
      tr(
        '可选模块缺失：{modules}。这通常会影响 VAD、STT/TTS 或 turnDetection 能力。',
        'Optional modules missing: {modules}. This can affect VAD, STT/TTS, or turnDetection capability.',
        { modules: pipecat.optionalMissingModules.join(', ') },
      ),
    )
  }
  if (pipecat.error) {
    addUniqueHint(
      hints,
      tr('Pipecat 检查错误：{message}', 'Pipecat check error: {message}', {
        message: sanitizeRealtimeDiagnosticText(pipecat.error),
      }),
    )
  }

  if (hints.length === 0) {
    hints.push(tr('没有发现阻塞项，可以尝试发起实时通话。', 'No blockers found; realtime calls can be started.'))
  }

  return hints
}

export default function TrainingStudioPage({ initialProfile = 'practice' }: TrainingStudioPageProps) {
  const navigate = useNavigate()
  const { locale, t, tr } = useI18n()
  const [config, setConfig] = useState<TrainingStudioConfig>(() => getDefaultTrainingStudioConfig(t))
  const previousDefaultsRef = useRef(getDefaultTrainingStudioConfig(t))
  const [mode, setMode] = useState<LaunchMode>(() => initialProfile === 'live_coach' ? 'live_coach' : 'voice')
  const [liveCoachSourceLanguage, setLiveCoachSourceLanguage] = useState('zh-CN')
  const [liveCoachTargetLanguage, setLiveCoachTargetLanguage] = useState('en-US')
  const [goal, setGoal] = useState('')
  const [starting, setStarting] = useState<'quick' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [realtimeCapabilities, setRealtimeCapabilities] = useState<RealtimeCapabilities | null>(null)
  const [realtimeCapabilitiesLoading, setRealtimeCapabilitiesLoading] = useState(false)
  const [realtimeCapabilitiesError, setRealtimeCapabilitiesError] = useState<string | null>(null)
  const [llmRegistry, setLlmRegistry] = useState<LLMProviderMetadata | null>(null)
  const [llmRegistryLoading, setLlmRegistryLoading] = useState(false)
  const [llmRegistryError, setLlmRegistryError] = useState<string | null>(null)

  const realtimeDiagnosticsVisible = mode === 'realtime' || mode === 'live_coach'

  const loadRealtimeCapabilities = useCallback(async () => {
    setRealtimeCapabilitiesLoading(true)
    setRealtimeCapabilitiesError(null)
    try {
      setRealtimeCapabilities(await fetchRealtimeCapabilities())
    } catch (requestError: unknown) {
      setRealtimeCapabilitiesError(getErrorMessage(
        requestError,
        tr('无法读取 Realtime / Pipecat 诊断。', 'Could not load Realtime / Pipecat diagnostics.'),
      ))
    } finally {
      setRealtimeCapabilitiesLoading(false)
    }
  }, [tr])

  const loadLlmRegistry = useCallback(async () => {
    setLlmRegistryLoading(true)
    setLlmRegistryError(null)
    try {
      setLlmRegistry(await fetchLlmRegistry())
    } catch (requestError: unknown) {
      setLlmRegistry(null)
      setLlmRegistryError(getErrorMessage(
        requestError,
        tr('Could not load provider/model registry.', 'Could not load provider/model registry.'),
      ))
    } finally {
      setLlmRegistryLoading(false)
    }
  }, [tr])

  useEffect(() => {
    if (initialProfile === 'live_coach') {
      setMode('live_coach')
    }
  }, [initialProfile])

  useEffect(() => {
    void loadRealtimeCapabilities()
  }, [loadRealtimeCapabilities])

  useEffect(() => {
    void loadLlmRegistry()
  }, [loadLlmRegistry])

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
    return buildTrainingStudioPrompt(config, `${base}\n\n${modeInstruction(mode, t)}`, t)
  }, [config, goal, mode, t])

  const llmModelChoices = useMemo(
    () => getLlmRegistryModelChoices(llmRegistry),
    [llmRegistry],
  )
  const capabilityReadiness = useMemo(
    () => buildTrainingStudioCapabilityReadiness({
      realtimeCapabilities,
      modelChoices: llmModelChoices,
      capabilityRegistry: (llmRegistry?.capability_registry ?? null) as RuntimeCapabilityRegistry | null,
    }),
    [llmModelChoices, llmRegistry, realtimeCapabilities],
  )
  const capabilityLoading = (realtimeCapabilitiesLoading && !realtimeCapabilities)
    || (llmRegistryLoading && !llmRegistry)
  const capabilityErrors = [
    realtimeCapabilitiesError,
    llmRegistryError,
  ].filter((message): message is string => Boolean(message))

  const openAIRealtimeStatus = realtimeCapabilities
    ? getOpenAIRealtimeStatus(realtimeCapabilities.openaiRealtime, tr)
    : { label: tr('读取中', 'Loading'), tone: 'loading' as const }
  const pipecatRealtimeStatus = realtimeCapabilities
    ? getPipecatRealtimeStatus(realtimeCapabilities.pipecat, tr)
    : { label: tr('读取中', 'Loading'), tone: 'loading' as const }
  const realtimeBlockingIssues = useMemo(
    () => realtimeCapabilities
      ? [
        ...mergeRealtimeIssues(
          realtimeCapabilities.openaiRealtime.readiness?.blockingReasons,
          realtimeCapabilities.openaiRealtime.errors,
        ),
        ...mergeRealtimeIssues(
          realtimeCapabilities.pipecat.readiness?.blockingReasons,
          realtimeCapabilities.pipecat.errors,
        ),
      ]
      : [],
    [realtimeCapabilities],
  )
  const realtimeReadinessHints = useMemo(
    () => realtimeCapabilities ? buildRealtimeReadinessHints(realtimeCapabilities, tr) : [],
    [realtimeCapabilities, tr],
  )
  const pipecatFeatureStatuses = realtimeCapabilities
    ? [
      { key: 'core', label: tr('Core', 'Core'), available: realtimeCapabilities.pipecat.coreAvailable },
      { key: 'websocket', label: tr('WebSocket', 'WebSocket'), available: realtimeCapabilities.pipecat.websocketAvailable },
      { key: 'vad', label: tr('VAD', 'VAD'), available: realtimeCapabilities.pipecat.vadAvailable },
      { key: 'stt', label: tr('STT', 'STT'), available: realtimeCapabilities.pipecat.sttAvailable },
      { key: 'tts', label: tr('TTS', 'TTS'), available: realtimeCapabilities.pipecat.ttsAvailable },
      { key: 'llm', label: tr('LLM', 'LLM'), available: realtimeCapabilities.pipecat.llmAvailable },
      { key: 'turnDetection', label: tr('turnDetection', 'turnDetection'), available: realtimeCapabilities.pipecat.turnDetectionAvailable },
    ]
    : []

  const startQuickSession = async () => {
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
      const modeLabel = getModeLabel(mode, t)
      const trainingProfile: TrainingProfile = mode === 'live_coach' ? 'live_coach' : 'practice'
      const isLiveCoachMode = trainingProfile === 'live_coach'
      const sourceLanguageLabel = getLiveCoachLanguageLabel(liveCoachSourceLanguage, locale)
      const targetLanguageLabel = getLiveCoachLanguageLabel(liveCoachTargetLanguage, locale)
      const interviewScenarioPreset = getInterviewScenarioPreset(config.interviewScenarioPreset)
      const productScenarioPreset = getProductScenarioPreset(config.productScenarioPreset)
      const interviewStakeholder = config.scenario === 'interview' ? interviewScenarioPreset : undefined
      const productStakeholder = config.scenario === 'product_management' ? productScenarioPreset : undefined
      const scenarioStakeholder = interviewStakeholder ?? productStakeholder
      const trainingSession = await createTrainingSession({
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
          metadata: isLiveCoachMode
            ? {
                source: 'live_coach_mvp',
                trainingProfile,
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
            : undefined,
        },
      })

      const useConversationMessageTreeRuntime = trainingMode === 'text' && interactionMode === 'turn_based'
      const room = useConversationMessageTreeRuntime
        ? null
        : await startBattle({
            persona_name: isLiveCoachMode
              ? t('training.liveCoach.personaName')
              : scenarioStakeholder
              ? t(scenarioStakeholder.personaNameKey)
              : t('training.prompt.personaName', { role }),
            persona_role: isLiveCoachMode
              ? t('training.liveCoach.personaRole')
              : scenarioStakeholder
              ? t(scenarioStakeholder.personaRoleKey)
              : t('training.prompt.personaRole', { level, scenario }),
            persona_style: isLiveCoachMode
              ? t('training.liveCoach.personaStyle')
              : scenarioStakeholder
              ? t(scenarioStakeholder.personaStyleKey, { difficulty, framework, mode: modeLabel })
              : t('training.prompt.personaStyle', { difficulty, framework, mode: modeLabel }),
            scenario_context: isLiveCoachMode
              ? `${prompt}\n\n${t('training.liveCoach.languageContext', {
                  sourceLanguage: sourceLanguageLabel,
                  targetLanguage: targetLanguageLabel,
                })}`
              : prompt,
            selected_training_points: isLiveCoachMode
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
                  t('training.prompt.deliveryPoint', { mode: modeLabel }),
                  t('training.prompt.evidencePoint'),
                ],
            difficulty: toBattleDifficulty(config.difficulty),
          })
      const startedSession = await startTrainingSession(
        trainingSession.session_id,
        buildTrainingSessionStartRequest(
          room ? { room_id: room.id } : {},
          trainingMode,
          interactionMode,
        ),
      )
      const roomId = startedSession.room_id ?? room?.id
      if (roomId == null) {
        throw new Error('Failed to resolve training room')
      }
      navigate(buildTrainingModeChatPath(roomId, trainingMode, startedSession.session_id, interactionMode, {
        trainingProfile,
        sourceLanguage: isLiveCoachMode ? liveCoachSourceLanguage : null,
        targetLanguage: isLiveCoachMode ? liveCoachTargetLanguage : null,
      }), {
        state: {
          source: isLiveCoachMode ? 'live-coach' : 'training-studio',
          trainingMode,
          interactionMode,
          trainingSessionId: startedSession.session_id,
          trainingProfile,
          sourceLanguage: isLiveCoachMode ? liveCoachSourceLanguage : undefined,
          targetLanguage: isLiveCoachMode ? liveCoachTargetLanguage : undefined,
        },
      })
    } catch (e: unknown) {
      setError(getErrorMessage(e, t('training.error.startFailed')))
      setStarting(null)
    }
  }

  const startGuidedBattle = async () => {
    navigate(APP_ROUTES.practiceBattle)
  }

  return (
    <div className="training-studio-page">
      <div className="training-studio-shell">
        <header className="training-studio-header">
          <div>
            <h1>{t('training.page.title')}</h1>
            <p>{t('training.page.subtitle')}</p>
          </div>
          <div className="training-studio-header-actions" aria-label={t('training.side.aria')}>
            <button
              className="training-studio-action"
              type="button"
              onClick={startQuickSession}
              disabled={starting !== null}
            >
              {starting === 'quick' ? <Loader2 size={16} className="training-studio-spin" /> : <Wand2 size={16} />}
              {t('training.page.startRoom')}
            </button>
            <button
              className="training-studio-action secondary"
              type="button"
              onClick={startGuidedBattle}
              disabled={starting !== null}
            >
              <Wand2 size={16} />
              {t('training.launch.openBattlePrep')}
            </button>
            {error && <div className="training-studio-error">{error}</div>}
          </div>
        </header>

        <section
          className="training-studio-capability-panel"
          aria-label={tr('Backend capability readiness', 'Backend capability readiness')}
          aria-live="polite"
        >
          <div className="training-studio-capability-header">
            <div>
              <span className="training-studio-capability-kicker">
                <ShieldCheck size={14} />
                {tr('Mature foundation alignment', 'Mature foundation alignment')}
              </span>
              <h2>{tr('Runtime, model, realtime, and agent readiness', 'Runtime, model, realtime, and agent readiness')}</h2>
              <p>
                {tr(
                  'Provider/model catalog, Realtime/Pipecat diagnostics, branch-aware review metadata, and agent/MCP capability signals are shown as product status without exposing secrets.',
                  'Provider/model catalog, Realtime/Pipecat diagnostics, branch-aware review metadata, and agent/MCP capability signals are shown as product status without exposing secrets.',
                )}
              </p>
            </div>
            <div className="training-studio-capability-actions">
              <span className={`training-studio-capability-status ${capabilityReadiness.overallStatus}`}>
                {capabilityStatusIcon(capabilityReadiness.overallStatus, capabilityLoading)}
                {capabilityStatusLabel(capabilityReadiness.overallStatus, tr)}
              </span>
              <button
                type="button"
                onClick={() => {
                  void loadRealtimeCapabilities()
                  void loadLlmRegistry()
                }}
                disabled={realtimeCapabilitiesLoading || llmRegistryLoading}
              >
                {(realtimeCapabilitiesLoading || llmRegistryLoading)
                  ? <Loader2 size={14} className="training-studio-spin" />
                  : <RefreshCw size={14} />}
                {tr('Refresh', 'Refresh')}
              </button>
            </div>
          </div>

          {capabilityErrors.length > 0 && (
            <div className="training-studio-capability-alerts">
              {capabilityErrors.map((message) => (
                <div key={message}>
                  <AlertTriangle size={14} />
                  <span>{sanitizeRealtimeDiagnosticText(message)}</span>
                </div>
              ))}
            </div>
          )}

          <div className="training-studio-capability-grid">
            {[...capabilityReadiness.foundation, capabilityReadiness.agentMcp].map((item: TrainingStudioCapabilityItem) => (
              <article className={`training-studio-capability-card ${item.status}`} key={item.key}>
                <div className="training-studio-capability-card-head">
                  <h3>{item.label}</h3>
                  <span className={`training-studio-capability-status ${item.status}`}>
                    {capabilityStatusIcon(item.status, capabilityLoading)}
                    {capabilityStatusLabel(item.status, tr)}
                  </span>
                </div>
                <p>{item.detail}</p>
                <dl>
                  {item.metrics.map((metric) => (
                    <div key={`${item.key}:${metric.label}`}>
                      <dt>{metric.label}</dt>
                      <dd>{metric.value}</dd>
                    </div>
                  ))}
                </dl>
                {item.tags.length > 0 && (
                  <div className="training-studio-capability-tags">
                    {item.tags.slice(0, 5).map((tag) => (
                      <span key={`${item.key}:${tag}`} title={tag}>{compactCapabilityTag(tag)}</span>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>

        <section className="training-studio-mode-panel" aria-label={t('training.page.responseModeAria')}>
          {modeOptions.map((item) => {
            const Icon = item.icon
            const selected = isModeCardSelected(item.value, mode)
            return (
              <div
                key={item.value}
                className={`training-studio-mode ${selected ? 'selected' : ''}`}
              >
                <button
                  className="training-studio-mode-main"
                  type="button"
                  onClick={() => setMode(item.defaultMode)}
                  disabled={starting !== null}
                  aria-pressed={selected}
                >
                  <Icon size={20} />
                  <span>{t(item.labelKey)}</span>
                  <small>{t(item.descriptionKey)}</small>
                </button>
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
                        <button
                          key={option.id}
                          className={`training-studio-interaction ${optionSelected ? 'selected' : ''}`}
                          type="button"
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
                            {option.badgeKey && <em>{t(option.badgeKey)}</em>}
                          </span>
                          <small>{t(option.descriptionKey)}</small>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </section>

        {realtimeDiagnosticsVisible && (
          <section
            className="training-studio-realtime-diagnostics"
            aria-label={tr('Realtime / Pipecat 就绪诊断', 'Realtime / Pipecat readiness diagnostics')}
            aria-live="polite"
          >
            <div className="training-studio-realtime-diagnostics-header">
              <div>
                <span className="training-studio-realtime-kicker">
                  <ShieldCheck size={14} />
                  {tr('通话前诊断', 'Pre-call diagnostics')}
                </span>
                <h2>{tr('Realtime / Pipecat readiness', 'Realtime / Pipecat readiness')}</h2>
                <p>
                  {tr(
                    '读取后端 /realtime/capabilities，仅展示配置状态、模块状态和错误元数据，不展示任何密钥。',
                    'Reads backend /realtime/capabilities and shows only config state, module state, and error metadata. Secrets are never displayed.',
                  )}
                </p>
              </div>
              <button
                className="training-studio-realtime-refresh"
                type="button"
                onClick={() => void loadRealtimeCapabilities()}
                disabled={realtimeCapabilitiesLoading}
              >
                {realtimeCapabilitiesLoading ? <Loader2 size={14} className="training-studio-spin" /> : <RefreshCw size={14} />}
                {tr('刷新', 'Refresh')}
              </button>
            </div>

            {realtimeCapabilitiesError && (
              <div className="training-studio-realtime-alert">
                <AlertTriangle size={15} />
                <span>{sanitizeRealtimeDiagnosticText(realtimeCapabilitiesError)}</span>
              </div>
            )}

            {realtimeCapabilitiesLoading && !realtimeCapabilities ? (
              <div className="training-studio-realtime-loading">
                <Loader2 size={16} className="training-studio-spin" />
                <span>{tr('正在读取 Realtime / Pipecat 诊断...', 'Loading Realtime / Pipecat diagnostics...')}</span>
              </div>
            ) : realtimeCapabilities ? (
              <>
                <div className="training-studio-realtime-provider-grid">
                  <article className={`training-studio-realtime-provider ${openAIRealtimeStatus.tone}`}>
                    <div className="training-studio-realtime-provider-head">
                      <div>
                        <h3>{tr('OpenAI Realtime', 'OpenAI Realtime')}</h3>
                        <span>{tr('密钥、模型、声音配置', 'Key, model, and voice config')}</span>
                      </div>
                      <span className={`training-studio-realtime-status ${openAIRealtimeStatus.tone}`}>
                        {realtimeStatusIcon(openAIRealtimeStatus.tone)}
                        {openAIRealtimeStatus.label}
                      </span>
                    </div>
                    <dl className="training-studio-realtime-metrics">
                      <div>
                        <dt>readyForCall</dt>
                        <dd>{formatBooleanStatus(Boolean(realtimeCapabilities.openaiRealtime.readyForCall), tr)}</dd>
                      </div>
                      <div>
                        <dt>readiness.status</dt>
                        <dd>{cleanDiagnosticText(realtimeCapabilities.openaiRealtime.readiness?.status) || tr('未知', 'Unknown')}</dd>
                      </div>
                      <div>
                        <dt>effectiveKey</dt>
                        <dd>{formatBooleanStatus(realtimeCapabilities.openaiRealtime.effectiveKey, tr)}</dd>
                      </div>
                      <div>
                        <dt>configured</dt>
                        <dd>{formatBooleanStatus(realtimeCapabilities.openaiRealtime.configured, tr)}</dd>
                      </div>
                      <div>
                        <dt>model</dt>
                        <dd>{cleanDiagnosticText(realtimeCapabilities.openaiRealtime.model) || tr('未配置', 'Not configured')}</dd>
                      </div>
                      <div>
                        <dt>voice</dt>
                        <dd>{cleanDiagnosticText(realtimeCapabilities.openaiRealtime.voice) || tr('未配置', 'Not configured')}</dd>
                      </div>
                      <div>
                        <dt>checkedAt</dt>
                        <dd>{cleanDiagnosticText(realtimeCapabilities.openaiRealtime.readiness?.checkedAt) || tr('未返回', 'Not returned')}</dd>
                      </div>
                    </dl>
                  </article>

                  <article className={`training-studio-realtime-provider ${pipecatRealtimeStatus.tone}`}>
                    <div className="training-studio-realtime-provider-head">
                      <div>
                        <h3>{tr('Pipecat pipeline', 'Pipecat pipeline')}</h3>
                        <span>{tr('模块、WebSocket、STT/TTS/LLM/VAD/turnDetection', 'Modules, WebSocket, STT/TTS/LLM/VAD/turnDetection')}</span>
                      </div>
                      <span className={`training-studio-realtime-status ${pipecatRealtimeStatus.tone}`}>
                        {realtimeStatusIcon(pipecatRealtimeStatus.tone)}
                        {pipecatRealtimeStatus.label}
                      </span>
                    </div>
                    <dl className="training-studio-realtime-metrics">
                      <div>
                        <dt>readyForCall</dt>
                        <dd>{formatBooleanStatus(realtimeCapabilities.pipecat.readyForCall, tr)}</dd>
                      </div>
                      <div>
                        <dt>readiness.status</dt>
                        <dd>{cleanDiagnosticText(realtimeCapabilities.pipecat.readiness?.status) || tr('未知', 'Unknown')}</dd>
                      </div>
                      <div>
                        <dt>available</dt>
                        <dd>{formatBooleanStatus(realtimeCapabilities.pipecat.available, tr)}</dd>
                      </div>
                      <div>
                        <dt>checkedAt</dt>
                        <dd>{cleanDiagnosticText(realtimeCapabilities.pipecat.readiness?.checkedAt) || tr('未返回', 'Not returned')}</dd>
                      </div>
                    </dl>
                    <div className="training-studio-realtime-feature-grid">
                      {pipecatFeatureStatuses.map((feature) => (
                        <span
                          key={feature.key}
                          className={`training-studio-realtime-feature ${feature.available ? 'ready' : 'blocked'}`}
                        >
                          {feature.available ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                          {feature.label}
                        </span>
                      ))}
                    </div>
                  </article>
                </div>

                <div className="training-studio-realtime-detail-grid">
                  <section className="training-studio-realtime-detail">
                    <div className="training-studio-realtime-detail-head">
                      <h3>{tr('blockingReasons / errors', 'blockingReasons / errors')}</h3>
                      <span>{realtimeBlockingIssues.length}</span>
                    </div>
                    {realtimeBlockingIssues.length > 0 ? (
                      <ul className="training-studio-realtime-issue-list">
                        {realtimeBlockingIssues.map((issue) => (
                          <li key={issueSignature(issue)}>
                            <strong>{formatRealtimeIssueTitle(issue, tr)}</strong>
                            <span>{formatRealtimeIssueDetail(issue, tr)}</span>
                            {(issue.modules?.length || issue.missingEnv?.length) ? (
                              <div className="training-studio-realtime-issue-tags">
                                {issue.modules?.map((moduleName) => (
                                  <em key={`module-${moduleName}`}>{sanitizeRealtimeDiagnosticText(moduleName)}</em>
                                ))}
                                {issue.missingEnv?.map((envName) => (
                                  <em key={`env-${envName}`}>{sanitizeRealtimeDiagnosticText(envName)}</em>
                                ))}
                              </div>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>{tr('没有 blockingReasons 或 errors。', 'No blockingReasons or errors returned.')}</p>
                    )}
                  </section>

                  <section className="training-studio-realtime-detail">
                    <div className="training-studio-realtime-detail-head">
                      <h3>{tr('可读提示', 'Readable hints')}</h3>
                      <span>{realtimeReadinessHints.length}</span>
                    </div>
                    <ul className="training-studio-realtime-hint-list">
                      {realtimeReadinessHints.map((hint) => (
                        <li key={hint}>{hint}</li>
                      ))}
                    </ul>
                    {(realtimeCapabilities.pipecat.missingModules.length > 0 || realtimeCapabilities.pipecat.optionalMissingModules.length > 0) && (
                      <div className="training-studio-realtime-module-row">
                        {realtimeCapabilities.pipecat.missingModules.map((moduleName) => (
                          <span key={`missing-${moduleName}`}>{sanitizeRealtimeDiagnosticText(moduleName)}</span>
                        ))}
                        {realtimeCapabilities.pipecat.optionalMissingModules.map((moduleName) => (
                          <span key={`optional-${moduleName}`} className="optional">{sanitizeRealtimeDiagnosticText(moduleName)}</span>
                        ))}
                      </div>
                    )}
                  </section>
                </div>
              </>
            ) : null}
          </section>
        )}

        <div className="training-studio-grid">
          <div className="training-studio-main">
            <label className="training-studio-goal">
              <span>{t('training.goal.label')}</span>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={4}
                placeholder={t('training.goal.placeholder')}
                disabled={starting !== null}
              />
            </label>

            {mode === 'live_coach' && (
              <section className="training-studio-live-coach-panel" aria-label={t('training.liveCoach.panelAria')}>
                <label>
                  <span>{t('training.liveCoach.sourceLanguage')}</span>
                  <select
                    value={liveCoachSourceLanguage}
                    onChange={(event) => setLiveCoachSourceLanguage(event.target.value)}
                    disabled={starting !== null}
                  >
                    {LIVE_COACH_LANGUAGE_OPTIONS.map((option) => (
                      <option key={option.code} value={option.code}>
                        {getLiveCoachLanguageLabel(option.code, locale)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>{t('training.liveCoach.targetLanguage')}</span>
                  <select
                    value={liveCoachTargetLanguage}
                    onChange={(event) => setLiveCoachTargetLanguage(event.target.value)}
                    disabled={starting !== null}
                  >
                    {LIVE_COACH_LANGUAGE_OPTIONS.map((option) => (
                      <option key={option.code} value={option.code}>
                        {getLiveCoachLanguageLabel(option.code, locale)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="training-studio-live-coach-badge">
                  <Languages size={14} />
                  {t('training.liveCoach.languageAdapter')}
                </div>
              </section>
            )}

            <TrainingStudioLauncher value={config} onChange={setConfig} disabled={starting !== null} />
          </div>
        </div>
      </div>
    </div>
  )
}
