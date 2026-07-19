import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import {
  MessageCircle,
  Plus,
  Activity,
  BarChart3,
  BarChart2,
  GraduationCap,
  Download,
  FileText,
  FileDown,
  Zap,
  Flag,
  Loader2,
  CheckCircle2,
  ChevronDown,
  ArrowLeft,
  ListTree,
  Route,
  PhoneCall,
  Volume2,
  VolumeX,
  Video,
  X,
  Lightbulb,
  Radio,
  Languages,
} from 'lucide-react'
import { useAppContext } from '../contexts/AppContext'
import { ChatProvider, useChatContext } from '../contexts/ChatContext'
import RoomList from '../components/RoomList'
import CreateRoomDialog from '../components/CreateRoomDialog'
import MessageList, { type MessageTreePathSelection } from '../components/chat/MessageList'
import ChatInput from '../components/chat/ChatInput'
import type { VoiceRecorderState } from '../components/VoiceRecorder'
import RealtimeVoiceRecorder from '../components/RealtimeVoiceRecorder'
import VideoAnswerRecorder, { type VideoAnswerResult } from '../components/VideoAnswerRecorder'
import ContextPanel from '../components/chat/ContextPanel'
import CoachingPanel from '../components/chat/CoachingPanel'
import AnalysisPanel from '../components/chat/AnalysisPanel'
import EmotionCurve from '../components/EmotionCurve'
import EmotionSidebar from '../components/EmotionSidebar'
import CheatSheetComponent from '../components/CheatSheet'
import {
  exportRoom,
  exportRoomHtml,
  generateCheatSheet,
  type ChatRoom,
  type CheatSheet as CheatSheetData,
  type Message as ChatMessage,
} from '../services/api'
import {
  completeTrainingSession,
  buildTrainingCompletionBranchMetadata,
  getTrainingGuidanceStreamUrl,
  getTrainingSessionReport,
  persistTrainingGuidanceEvents,
  requestTrainingGuidance,
  type GuideEventDTO,
  type TrainingSessionReportDTO,
  type TrainingGuidanceResponse,
  type TranscriptTurnDTO,
} from '../services/trainingSession'
import { uploadVideoAnswer } from '../services/trainingStudio'
import {
  fetchLlmRegistry,
  getLlmRegistryModelChoices,
  isLlmModelChoiceSelectable,
  selectDefaultLlmModelChoice,
  type LLMModelChoice,
  type LLMProviderMetadata,
} from '../services/llmRegistry'
import {
  getInteractionModeFromLocation,
  getLiveCoachLanguagePairFromLocation,
  getTrainingProfileFromLocation,
  getTrainingModeFromLocation,
  getTrainingSessionIdFromLocation,
  isTrainingModeBattlePrep,
} from '../services/trainingMode'
import {
  findScenarioTrainingIdBySession,
  getScenarioTrainingCardById,
  getScenarioTrainingProgress,
  markScenarioTrainingCompleted,
  saveScenarioTrainingProgress,
  type ScenarioTrainingCategory,
  type ScenarioTrainingDifficulty,
  type ScenarioTrainingProgressScope,
} from '../data/trainingScenarios'
import { getLiveCoachLanguageLabel } from '../data/liveCoachLanguages'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n, type Translate, type TranslateInline } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { getErrorMessage } from '../utils/errors'
import {
  getScenarioCategoryLabel,
  getScenarioDifficultyLabel,
} from '../utils/scenarioLabels'
import '../App.css'
import './ChatPage.css'

function displayInitial(name: string): string {
  const first = name.trim().charAt(0)
  if (!first) return '?'
  return /[a-z]/i.test(first) ? first.toUpperCase() : first
}

function getScenarioTrainingIdFromLocation(search: string, state: unknown): string | null {
  const stateValue = state && typeof state === 'object'
    ? (state as { scenarioTrainingId?: unknown }).scenarioTrainingId
    : undefined
  if (typeof stateValue === 'string' && stateValue.trim()) {
    return stateValue.trim()
  }
  const value = new URLSearchParams(search).get('scenarioTrainingId')
  return value?.trim() || null
}

function getScenarioTrainingIdFromProgress(
  trainingSessionId: string | null,
  scope?: ScenarioTrainingProgressScope,
): string | null {
  return findScenarioTrainingIdBySession(getScenarioTrainingProgress(scope), trainingSessionId)
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function getStateStringValue(state: unknown, key: string): string | null {
  const value = asRecord(state)?.[key]
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function getStateStringArrayValue(state: unknown, key: string): string[] {
  const value = asRecord(state)?.[key]
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function getStateBooleanValue(state: unknown, key: string): boolean | null {
  const value = asRecord(state)?.[key]
  return typeof value === 'boolean' ? value : null
}

function getScenarioDifficultyFromState(state: unknown): ScenarioTrainingDifficulty | null {
  const value = getStateStringValue(state, 'scenarioDifficulty')
  return value === 'easy' || value === 'medium' || value === 'hard' || value === 'expert' ? value : null
}

function getScenarioCategoryFromState(state: unknown): ScenarioTrainingCategory | null {
  const value = getStateStringValue(state, 'scenarioCategory')
  return value === 'sales' || value === 'customer_service' || value === 'negotiation' || value === 'interview' || value === 'workplace'
    ? value
    : null
}

function compactStrings(values: Array<string | null | undefined | false>): string[] {
  return values.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
}

function compactTreeNodeContent(
  item: MessageTreePathSelection['path'][number],
  fallback: string,
): string {
  const text = item.content.replace(/\s+/g, ' ').trim()
  if (!text) return fallback
  return text.length > 72 ? `${text.slice(0, 71)}...` : text
}

function findMessageTreeForkPoint(
  path: MessageTreePathSelection['path'],
): MessageTreePathSelection['path'][number] | null {
  for (let index = 1; index < path.length; index += 1) {
    const previous = path[index - 1]
    const current = path[index]
    if (!current.branchId || current.branchId === previous.branchId) continue
    return previous
  }
  return null
}

type TrainingContextTag = {
  label: string
  tone?: 'category' | 'difficulty' | 'required' | 'optional' | 'mode' | 'live'
}

function compactTags(values: Array<TrainingContextTag | null | undefined | false>): TrainingContextTag[] {
  return values.filter((value): value is TrainingContextTag => (
    Boolean(value && typeof value === 'object' && value.label.trim())
  ))
}

function mergeMetadata(
  ...items: Array<Record<string, unknown> | null | undefined>
): Record<string, unknown> | undefined {
  const merged = Object.assign({}, ...items.filter(Boolean))
  return Object.keys(merged).length > 0 ? merged : undefined
}

function buildLlmSelectionMetadata(choice: LLMModelChoice | null): Record<string, unknown> | undefined {
  if (!choice) return undefined
  return {
    provider: choice.provider,
    model: choice.model,
    llm_provider: choice.provider,
    llm_model: choice.model,
    llm: {
      provider: choice.provider,
      model: choice.model,
      model_spec: choice.modelSpec?.name ?? null,
      endpoint: choice.endpoint,
      wire_api: choice.wireApi,
      capabilities: choice.capabilities,
      context_window: choice.contextWindow,
      max_output_tokens: choice.maxOutputTokens,
      source: 'training_room_selector',
    },
  }
}

function formatCompactTokenCount(value: number | null): string | null {
  if (!value || value <= 0) return null
  const formatUnit = (amount: number, suffix: string) => {
    const rounded = Math.round(amount * 10) / 10
    return `${Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)}${suffix}`
  }
  if (value >= 1_000_000) return formatUnit(value / 1_000_000, 'M')
  if (value >= 1_000) return formatUnit(value / 1_000, 'K')
  return String(value)
}

function getLlmCapabilityLabel(capability: string, t: Translate): string {
  const normalized = capability.trim().toLowerCase().replace(/[\s-]+/g, '_')
  switch (normalized) {
    case 'vision':
      return t('training.llm.capability.vision')
    case 'tools':
    case 'tool_use':
    case 'function_calling':
      return t('training.llm.capability.tools')
    case 'reasoning':
      return t('training.llm.capability.reasoning')
    case 'audio':
      return t('training.llm.capability.audio')
    case 'realtime':
      return t('training.llm.capability.realtime')
    case 'image':
    case 'image_generation':
      return t('training.llm.capability.image')
    default:
      return capability.replace(/[_-]+/g, ' ')
  }
}

type LlmDetailTag = {
  key: string
  label: string
  tone?: 'warning'
}

function buildLlmDetailTags(choice: LLMModelChoice | null, t: Translate): LlmDetailTag[] {
  if (!choice) return []
  const contextCount = formatCompactTokenCount(choice.contextWindow)
  const outputCount = formatCompactTokenCount(choice.maxOutputTokens)
  const tags: LlmDetailTag[] = compactStrings([
    contextCount ? t('training.llm.contextTag', { count: contextCount }) : null,
    outputCount ? t('training.llm.maxOutputTag', { count: outputCount }) : null,
    ...choice.capabilities.slice(0, 4).map((capability) => getLlmCapabilityLabel(capability, t)),
  ]).map((label) => ({ key: label, label }))
  if (choice.disabled) {
    tags.push({ key: 'unavailable', label: t('training.llm.unavailableTag'), tone: 'warning' })
  }
  return tags
}

function formatLlmOptionLabel(choice: LLMModelChoice, t: Translate): string {
  const badges = compactStrings([
    choice.isDefault ? t('training.llm.defaultBadge') : null,
    choice.disabled ? t('training.llm.unavailableTag') : null,
  ])
  return badges.length > 0 ? `${choice.modelLabel} (${badges.join(' / ')})` : choice.modelLabel
}

function coercePercentScore(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined
  return Math.max(0, Math.min(100, Math.round(value)))
}

function extractTrainingReportScore(report: TrainingSessionReportDTO): number | undefined {
  const content = asRecord(report.content)
  if (!content) return undefined
  for (const key of ['content_delivery', 'camera_presence']) {
    const dimension = asRecord(content[key])
    const score = coercePercentScore(dimension?.score)
    if (score !== undefined) return score
  }
  return coercePercentScore(content.score)
}

const GUIDANCE_TURN_WINDOW = 8
const GUIDANCE_AUTO_DELAY_MS = 900
const GUIDANCE_AUTO_MIN_INTERVAL_MS = 1200

const GUIDE_EVENT_TEXTS: Record<string, [string, string]> = {
  'Ask a calibration question': ['追问校准问题', 'Ask a calibration question'],
  'Discovery gap': ['发现信息缺口', 'Discovery gap'],
  'Objection surfaced': ['异议浮现', 'Objection surfaced'],
  'Next reply candidate': ['下一句候选', 'Next reply candidate'],
  'Risk surfaced': ['风险浮现', 'Risk surfaced'],
  'Tighten the delivery': ['收紧表达', 'Tighten the delivery'],
  'Delivery nudge': ['表达提醒', 'Delivery nudge'],
  'You have not asked a question in the recent window. Pull out the counterpart\'s priority before continuing.': [
    '最近几轮你还没有提问。继续推进前，先问出对方真正优先级。',
    'You have not asked a question in the recent window. Pull out the counterpart\'s priority before continuing.',
  ],
  'The recent exchange is light on discovery. Add one focused question before pitching or defending.': [
    '最近对话的信息探索偏少。在陈述或防守前，先补一个聚焦问题。',
    'The recent exchange is light on discovery. Add one focused question before pitching or defending.',
  ],
  'The counterpart just signaled resistance. Acknowledge it before adding more evidence.': [
    '对方刚释放出阻力信号。先承认这一点，再补充证据。',
    'The counterpart just signaled resistance. Acknowledge it before adding more evidence.',
  ],
  'A compact next move based on the current bounded transcript window.': [
    '基于当前对话窗口生成的简短下一步建议。',
    'A compact next move based on the current bounded transcript window.',
  ],
  'Your last answer is running long. Land the point, pause, and invite the other side in.': [
    '你上一段回答偏长。先落到重点，停顿一下，把对方带回来。',
    'Your last answer is running long. Land the point, pause, and invite the other side in.',
  ],
  'Before I go further, what matters most to you in this situation?': [
    '在继续之前，我想先确认：这个场景里你最在意什么？',
    'Before I go further, what matters most to you in this situation?',
  ],
  'What constraint or success metric should I optimize for?': [
    '我应该优先满足哪个约束或成功指标？',
    'What constraint or success metric should I optimize for?',
  ],
  'That concern makes sense. Can I check whether the main issue is impact, cost, or timing?': [
    '这个担心有道理。我可以确认一下，核心问题是影响、成本还是时间吗？',
    'That concern makes sense. Can I check whether the main issue is impact, cost, or timing?',
  ],
  'Start by clarifying the goal and asking what the other side cares about most.': [
    '先确认目标，再问对方最在意什么。',
    'Start by clarifying the goal and asking what the other side cares about most.',
  ],
  'Acknowledge their point, ask one clarifying question, then give a concise answer.': [
    '先承认对方观点，追问一个澄清问题，再给出简洁回应。',
    'Acknowledge their point, ask one clarifying question, then give a concise answer.',
  ],
  'Give the short answer first, support it with one example, then pause.': [
    '先给短答案，用一个例子支撑，然后停顿。',
    'Give the short answer first, support it with one example, then pause.',
  ],
  'Let me pause there. Which part would you like me to go deeper on?': [
    '我先停在这里。你希望我在哪一部分展开？',
    'Let me pause there. Which part would you like me to go deeper on?',
  ],
}

const GUIDE_EVENT_TYPE_LABELS: Record<string, [string, string]> = {
  next_reply: ['下一句', 'Next reply'],
  risk: ['风险', 'Risk'],
  omission: ['缺口', 'Omission'],
  ask_back: ['追问', 'Ask back'],
  delivery_nudge: ['表达', 'Delivery'],
}

type LocalizedGuideEvent = GuideEventDTO & {
  displayTitle: string
  displayMessage: string
  displaySuggestedText?: string
  displayType: string
}

function localizeKnownGuideText(text: string | undefined, tr: TranslateInline): string | undefined {
  if (!text) return text
  const mapped = GUIDE_EVENT_TEXTS[text.trim()]
  return mapped ? tr(mapped[0], mapped[1]) : text
}

function localizeGuideEvent(event: GuideEventDTO, tr: TranslateInline): LocalizedGuideEvent {
  const type = GUIDE_EVENT_TYPE_LABELS[event.event_type]
  return {
    ...event,
    displayTitle: localizeKnownGuideText(event.title, tr) || event.title,
    displayMessage: localizeKnownGuideText(event.message, tr) || event.message,
    displaySuggestedText: localizeKnownGuideText(event.suggested_text, tr),
    displayType: type ? tr(type[0], type[1]) : event.event_type.replace(/_/g, ' '),
  }
}

function guidanceEventsSignature(events: GuideEventDTO[]): string {
  return JSON.stringify(events.map((event) => {
    const stableEvent = { ...event }
    delete stableEvent.created_at
    return stableEvent
  }))
}

function getTrainingModeLabel(mode: string, tr: TranslateInline): string {
  if (mode === 'text') return tr('文本', 'Text')
  if (mode === 'voice') return tr('语音', 'Voice')
  if (mode === 'video') return tr('视频', 'Video')
  if (mode === 'live_coach') return tr('实时教练', 'Live coach')
  return mode
}

function getInteractionModeLabel(mode: string, tr: TranslateInline): string {
  if (mode === 'turn_based') return tr('轮次对练', 'Turn-based')
  if (mode === 'realtime') return tr('实时对练', 'Realtime')
  return mode
}

type RefreshGuidanceOptions = {
  open?: boolean
  extraTurn?: TranscriptTurnDTO
  autoOpenOnSignal?: boolean
  minIntervalMs?: number
}

/* ------------------------------------------------------------------ */
/*  Inner chat area — must be inside ChatProvider                      */
/* ------------------------------------------------------------------ */

function ChatArea() {
  const { personaMap } = useAppContext()
  const { chat, voice, coaching, analysis } = useChatContext()
  const { currentUser } = useAuthContext()
  const navigate = useNavigate()
  const location = useLocation()
  const { locale, t, tr } = useI18n()
  const preparedVoiceRoomRef = React.useRef<number | null>(null)
  const guidanceTurnsRef = React.useRef<TranscriptTurnDTO[]>([])
  const guidanceTimerRef = React.useRef<number | null>(null)
  const guidanceInFlightRef = React.useRef(false)
  const guidanceRequestSeqRef = React.useRef(0)
  const guidanceLastRequestedAtRef = React.useRef(0)
  const lastAutoGuidanceMessageKeyRef = React.useRef<string | null>(null)
  const persistedGuidanceSignatureRef = React.useRef<string | null>(null)
  const guidanceEventSourceRef = React.useRef<EventSource | null>(null)
  const guidanceStreamVersionRef = React.useRef(0)
  const trainingMode = getTrainingModeFromLocation(location.search, location.state)
  const interactionMode = getInteractionModeFromLocation(location.search, location.state)
  const trainingSessionId = getTrainingSessionIdFromLocation(location.search, location.state)
  const trainingProfile = getTrainingProfileFromLocation(location.search, location.state)
  const liveCoachLanguagePair = getLiveCoachLanguagePairFromLocation(location.search, location.state)
  const isLiveCoachSession = trainingProfile === 'live_coach'
  const isTrainingSession = Boolean(trainingSessionId)
  const progressScope = React.useMemo(() => ({
    userId: currentUser?.userId ?? null,
    teamId: currentUser?.teamId ?? null,
  }), [currentUser?.teamId, currentUser?.userId])
  const scenarioTrainingId = getScenarioTrainingIdFromLocation(location.search, location.state)
    ?? getScenarioTrainingIdFromProgress(trainingSessionId, progressScope)
  const scenarioTrainingCard = getScenarioTrainingCardById(scenarioTrainingId)
  const hasScenarioTrainingContext = Boolean(
    scenarioTrainingCard
    || scenarioTrainingId
    || getStateStringValue(location.state, 'source') === 'scenario-training',
  )

  const [showEmotionSidebar, setShowEmotionSidebar] = useState(false)
  const [showEmotionCurve, setShowEmotionCurve] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [showContextPanel, setShowContextPanel] = useState(false)
  const [mobileSheet, setMobileSheet] = useState<string | null>(null)
  const [lastVoiceTranscript, setLastVoiceTranscript] = useState<string | null>(null)
  const [voiceRecorderState, setVoiceRecorderState] = useState<VoiceRecorderState>('idle')
  const [voiceRecorderError, setVoiceRecorderError] = useState<string | null>(null)
  const [lastVideoAnswerAt, setLastVideoAnswerAt] = useState<string | null>(null)
  const [videoAnswerStatus, setVideoAnswerStatus] = useState<'idle' | 'uploading' | 'sent' | 'error'>('idle')
  const [videoAnswerError, setVideoAnswerError] = useState<string | null>(null)
  const [videoRecorderOpen, setVideoRecorderOpen] = useState(false)
  const [messageTreeSelection, setMessageTreeSelection] = useState<MessageTreePathSelection | null>(null)

  // Battle prep state
  const [battlePrepRoundCount, setBattlePrepRoundCount] = useState(0)
  const [battlePrepEnding, setBattlePrepEnding] = useState(false)
  const [trainingSessionCompleting, setTrainingSessionCompleting] = useState(false)
  const [trainingSessionCompleted, setTrainingSessionCompleted] = useState(false)
  const [guidanceOpen, setGuidanceOpen] = useState(false)
  const [guidanceLoading, setGuidanceLoading] = useState(false)
  const [guidanceError, setGuidanceError] = useState<string | null>(null)
  const [guidanceEvents, setGuidanceEvents] = useState<GuideEventDTO[]>([])
  const [guidanceStreamConnected, setGuidanceStreamConnected] = useState(false)
  const localizedGuidanceEvents = React.useMemo(
    () => guidanceEvents.map((event) => localizeGuideEvent(event, tr)),
    [guidanceEvents, tr],
  )
  const [cheatSheetData, setCheatSheetData] = useState<CheatSheetData | null>(null)
  const [cheatSheetPersona, setCheatSheetPersona] = useState('')
  const [trainingSceneExpanded, setTrainingSceneExpanded] = useState(false)
  const [llmRegistry, setLlmRegistry] = useState<LLMProviderMetadata | null>(null)
  const [selectedLlmChoiceKey, setSelectedLlmChoiceKey] = useState<string | null>(null)
  const selectedRoomId = chat.selectedRoom?.room.id ?? null
  const selectedRoomType = chat.selectedRoom?.room.type
  const sendChatMessage = chat.handleSend

  useEffect(() => {
    setMessageTreeSelection(null)
  }, [selectedRoomId])

  const sourceLanguageLabel = getLiveCoachLanguageLabel(liveCoachLanguagePair.sourceLanguage, locale)
  const targetLanguageLabel = getLiveCoachLanguageLabel(liveCoachLanguagePair.targetLanguage, locale)
  const liveCoachGuidanceMetadata = React.useMemo(() => {
    if (!isLiveCoachSession) return undefined
    return {
      source: 'live_coach_bilingual_mvp',
      trainingProfile,
      liveCoach: {
        sourceLanguage: liveCoachLanguagePair.sourceLanguage,
        targetLanguage: liveCoachLanguagePair.targetLanguage,
        sourceLanguageLabel,
        targetLanguageLabel,
      },
      translation: {
        mode: 'text_first_mvp',
        sourceLanguage: liveCoachLanguagePair.sourceLanguage,
        targetLanguage: liveCoachLanguagePair.targetLanguage,
        sourceLanguageLabel,
        targetLanguageLabel,
        preserveTone: true,
        supportedLanguages: '70_plus',
        extensionPoints: [
          'speech_to_speech_translation',
          'virtual_microphone',
          'prosody_preservation',
        ],
      },
    }
  }, [
    isLiveCoachSession,
    liveCoachLanguagePair.sourceLanguage,
    liveCoachLanguagePair.targetLanguage,
    sourceLanguageLabel,
    targetLanguageLabel,
    trainingProfile,
  ])
  const liveCoachRealtimeTranscriptMetadata = React.useMemo(() => (
    liveCoachGuidanceMetadata
      ? {
          ...liveCoachGuidanceMetadata,
          source: 'live_coach_realtime_voice',
        }
      : undefined
  ), [liveCoachGuidanceMetadata])

  useEffect(() => {
    let cancelled = false
    if (!isTrainingSession) {
      setLlmRegistry(null)
      setSelectedLlmChoiceKey(null)
      return () => {
        cancelled = true
      }
    }

    fetchLlmRegistry()
      .then((registry) => {
        if (!cancelled) setLlmRegistry(registry)
      })
      .catch((error) => {
        if (cancelled) return
        console.warn('Failed to fetch LLM registry:', error)
        setLlmRegistry(null)
      })

    return () => {
      cancelled = true
    }
  }, [isTrainingSession])

  const llmModelChoices = React.useMemo(
    () => getLlmRegistryModelChoices(llmRegistry),
    [llmRegistry],
  )
  const firstSelectableLlmChoice = React.useMemo(
    () => llmModelChoices.find(isLlmModelChoiceSelectable) ?? null,
    [llmModelChoices],
  )
  const selectedLlmChoice = React.useMemo(
    () => {
      const choice = llmModelChoices.find((item) => item.key === selectedLlmChoiceKey) ?? null
      return isLlmModelChoiceSelectable(choice) ? choice : null
    },
    [llmModelChoices, selectedLlmChoiceKey],
  )
  const selectedLlmProvider = selectedLlmChoice?.provider ?? firstSelectableLlmChoice?.provider ?? llmModelChoices[0]?.provider ?? ''
  const llmProviderOptions = React.useMemo(() => {
    const providers = new Map<string, string>()
    for (const choice of llmModelChoices) {
      if (!providers.has(choice.provider)) {
        providers.set(choice.provider, choice.providerLabel)
      }
    }
    return Array.from(providers, ([provider, label]) => ({ provider, label }))
  }, [llmModelChoices])
  const selectedProviderModelChoices = React.useMemo(
    () => llmModelChoices.filter((choice) => choice.provider === selectedLlmProvider),
    [llmModelChoices, selectedLlmProvider],
  )
  const displayedLlmChoice = selectedLlmChoice ?? selectedProviderModelChoices[0] ?? null
  const llmDetailTags = React.useMemo(
    () => buildLlmDetailTags(displayedLlmChoice, t),
    [displayedLlmChoice, t],
  )
  const llmSelectionMetadata = React.useMemo(
    () => buildLlmSelectionMetadata(selectedLlmChoice),
    [selectedLlmChoice],
  )
  const outgoingMessageMetadata = React.useMemo(
    () => mergeMetadata(liveCoachGuidanceMetadata, llmSelectionMetadata),
    [liveCoachGuidanceMetadata, llmSelectionMetadata],
  )

  useEffect(() => {
    setSelectedLlmChoiceKey((currentKey) => {
      if (llmModelChoices.length === 0) return null
      if (currentKey && llmModelChoices.some((choice) => choice.key === currentKey && isLlmModelChoiceSelectable(choice))) {
        return currentKey
      }
      return selectDefaultLlmModelChoice(llmRegistry)?.key ?? null
    })
  }, [llmModelChoices, llmRegistry])

  const handleLlmProviderChange = React.useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
    const provider = event.target.value
    const providerChoices = llmModelChoices.filter((choice) => choice.provider === provider)
    const nextChoice = providerChoices.find((choice) => choice.isDefault && isLlmModelChoiceSelectable(choice))
      ?? providerChoices.find(isLlmModelChoiceSelectable)
      ?? null
    setSelectedLlmChoiceKey(nextChoice?.key ?? null)
  }, [llmModelChoices])

  const handleLlmModelChange = React.useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextKey = event.target.value || null
    const nextChoice = llmModelChoices.find((choice) => choice.key === nextKey) ?? null
    setSelectedLlmChoiceKey(nextChoice && isLlmModelChoiceSelectable(nextChoice) ? nextChoice.key : null)
  }, [llmModelChoices])

  useEffect(() => {
    setTrainingSessionCompleted(false)
    setTrainingSceneExpanded(false)
    setGuidanceOpen(false)
    setGuidanceError(null)
    setGuidanceEvents([])
    setGuidanceStreamConnected(false)
    guidanceRequestSeqRef.current += 1
    lastAutoGuidanceMessageKeyRef.current = null
    persistedGuidanceSignatureRef.current = null
    if (guidanceTimerRef.current !== null) {
      window.clearTimeout(guidanceTimerRef.current)
      guidanceTimerRef.current = null
    }
    if (guidanceEventSourceRef.current) {
      guidanceStreamVersionRef.current += 1
      guidanceEventSourceRef.current.close()
      guidanceEventSourceRef.current = null
    }
  }, [trainingSessionId])

  useEffect(() => {
    return () => {
      if (guidanceTimerRef.current !== null) {
        window.clearTimeout(guidanceTimerRef.current)
      }
      if (guidanceEventSourceRef.current) {
        guidanceStreamVersionRef.current += 1
        guidanceEventSourceRef.current.close()
        guidanceEventSourceRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!trainingSessionId) return
    if (guidanceEventSourceRef.current) {
      guidanceStreamVersionRef.current += 1
      guidanceEventSourceRef.current.close()
      guidanceEventSourceRef.current = null
    }

    const streamVersion = guidanceStreamVersionRef.current + 1
    guidanceStreamVersionRef.current = streamVersion
    const es = new EventSource(getTrainingGuidanceStreamUrl(trainingSessionId, {
      message_limit: 50,
      poll_interval_ms: 1000,
    }))
    guidanceEventSourceRef.current = es
    setGuidanceLoading(true)
    setGuidanceError(null)

    const isCurrentStream = () =>
      guidanceEventSourceRef.current === es && guidanceStreamVersionRef.current === streamVersion

    es.addEventListener('guidance_snapshot', (event) => {
      if (!isCurrentStream()) return
      try {
        const data: TrainingGuidanceResponse = JSON.parse(event.data)
        setGuidanceStreamConnected(true)
        setGuidanceLoading(false)
        setGuidanceError(null)
        setGuidanceEvents(data.events)
        if (data.events.some((item) => item.severity !== 'info')) {
          setGuidanceOpen(true)
        }
      } catch {
        setGuidanceError(tr('实时提示流失败', 'Live guidance stream failed'))
      }
    })

    es.addEventListener('guidance_error', (event) => {
      if (!isCurrentStream()) return
      try {
        const data = JSON.parse(event.data)
        setGuidanceError(getErrorMessage(data, tr('实时提示流失败', 'Live guidance stream failed')))
      } catch {
        setGuidanceError(tr('实时提示流失败', 'Live guidance stream failed'))
      }
      setGuidanceLoading(false)
      setGuidanceStreamConnected(false)
    })

    es.onerror = () => {
      if (!isCurrentStream()) return
      setGuidanceLoading(false)
      setGuidanceStreamConnected(false)
    }

    return () => {
      guidanceStreamVersionRef.current += 1
      es.close()
      if (guidanceEventSourceRef.current === es) {
        guidanceEventSourceRef.current = null
      }
      setGuidanceStreamConnected(false)
    }
  }, [trainingSessionId, tr])

  // Compute battle prep round count from existing messages
  const selectedRoomMessages = chat.selectedRoom?.messages
  useEffect(() => {
    if (selectedRoomType === 'battle_prep' && selectedRoomMessages && selectedRoomMessages.length > 0) {
      const userMsgCount = selectedRoomMessages.filter((m: { sender_type: string }) => m.sender_type === 'user').length
      setBattlePrepRoundCount(userMsgCount)
    } else {
      setBattlePrepRoundCount(0)
    }
  }, [selectedRoomId, selectedRoomType, selectedRoomMessages])
  const guidanceTurns = React.useMemo<TranscriptTurnDTO[]>(() => {
    return ((selectedRoomMessages || []) as ChatMessage[])
      .filter((message) => message.content.trim())
      .slice(-GUIDANCE_TURN_WINDOW)
      .map((message) => ({
        speaker: message.sender_type === 'persona'
          ? 'counterpart'
          : message.sender_type === 'system'
            ? 'system'
            : 'user',
        text: message.content.trim(),
        turn_id: String(message.id),
        metadata: {
          ...(liveCoachGuidanceMetadata || {}),
          ...((message as { metadata?: Record<string, unknown> }).metadata || {}),
          room_id: message.room_id,
          sender_id: message.sender_id,
          sender_type: message.sender_type,
          emotion_score: message.emotion_score,
          emotion_label: message.emotion_label,
        },
      }))
  }, [liveCoachGuidanceMetadata, selectedRoomMessages])

  useEffect(() => {
    guidanceTurnsRef.current = guidanceTurns
  }, [guidanceTurns])

  const roomPersonas = chat.selectedRoom
    ? chat.selectedRoom.room.persona_ids
        .map((id) => personaMap[id])
        .filter(Boolean)
    : []

  const handleEndBattle = React.useCallback(async () => {
    if (!chat.selectedRoom || battlePrepEnding) return
    const personaId = chat.selectedRoom.room.persona_ids[0] || ''
    const persona = personaMap[personaId]
    setCheatSheetPersona(persona?.name || tr('对方', 'The other side'))
    setBattlePrepEnding(true)
    try {
      const sheet = await generateCheatSheet(chat.selectedRoom.room.id)
      setCheatSheetData(sheet)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : tr('话术纸条生成失败', 'Failed to generate cheat sheet'))
    } finally {
      setBattlePrepEnding(false)
    }
  }, [battlePrepEnding, chat.selectedRoom, personaMap, tr])

  const refreshGuidance = React.useCallback(async (options: RefreshGuidanceOptions = {}) => {
    if (!trainingSessionId) return
    if (guidanceInFlightRef.current) {
      if (options.open) setGuidanceOpen(true)
      return
    }
    const now = Date.now()
    const minInterval = options.minIntervalMs ?? 0
    if (minInterval > 0 && now - guidanceLastRequestedAtRef.current < minInterval) {
      const remaining = minInterval - (now - guidanceLastRequestedAtRef.current)
      if (guidanceTimerRef.current !== null) {
        window.clearTimeout(guidanceTimerRef.current)
      }
      guidanceTimerRef.current = window.setTimeout(() => {
        guidanceTimerRef.current = null
        void refreshGuidance({ ...options, minIntervalMs: 0 })
      }, remaining)
      return
    }

    const requestId = guidanceRequestSeqRef.current + 1
    guidanceRequestSeqRef.current = requestId
    guidanceLastRequestedAtRef.current = now
    guidanceInFlightRef.current = true
    if (options.open) setGuidanceOpen(true)
    setGuidanceLoading(true)
    setGuidanceError(null)

    const turns = [...guidanceTurnsRef.current]
    if (options.extraTurn?.text.trim()) {
      turns.push(options.extraTurn)
    }
    const requestBody = options.extraTurn
      ? {
          recent_turns: turns.slice(-GUIDANCE_TURN_WINDOW),
          message_limit: 50,
        }
      : { message_limit: 50 }

    try {
      const result = await requestTrainingGuidance(trainingSessionId, requestBody)
      if (guidanceRequestSeqRef.current !== requestId) return
      setGuidanceEvents(result.events)
      if (options.autoOpenOnSignal && result.events.some((event) => event.severity !== 'info')) {
        setGuidanceOpen(true)
      }
    } catch (e: unknown) {
      if (guidanceRequestSeqRef.current !== requestId) return
      setGuidanceError(e instanceof Error ? e.message : tr('实时提示失败', 'Live guidance failed'))
    } finally {
      guidanceInFlightRef.current = false
      if (guidanceRequestSeqRef.current === requestId) {
        setGuidanceLoading(false)
      }
    }
  }, [trainingSessionId, tr])

  const scheduleGuidanceRefresh = React.useCallback((options: RefreshGuidanceOptions = {}) => {
    if (!trainingSessionId || guidanceStreamConnected) return
    if (guidanceTimerRef.current !== null) {
      window.clearTimeout(guidanceTimerRef.current)
    }
    guidanceTimerRef.current = window.setTimeout(() => {
      guidanceTimerRef.current = null
      void refreshGuidance(options)
    }, GUIDANCE_AUTO_DELAY_MS)
  }, [guidanceStreamConnected, refreshGuidance, trainingSessionId])

  const handleSend = React.useCallback(async () => {
    const outgoingText = chat.inputValue.trim()
    const success = await sendChatMessage(outgoingMessageMetadata)
    if (!success) return
    if (trainingSessionId && outgoingText) {
      scheduleGuidanceRefresh({
        extraTurn: isLiveCoachSession
          ? {
              speaker: 'user',
              text: outgoingText,
              metadata: {
                ...(outgoingMessageMetadata || {}),
                source: 'live_coach_text_input',
                trainingMode,
                interactionMode,
              },
            }
          : undefined,
        minIntervalMs: GUIDANCE_AUTO_MIN_INTERVAL_MS,
      })
    }
    // Track battle prep rounds
    if (selectedRoomType === 'battle_prep' && !trainingSessionId) {
      const newCount = battlePrepRoundCount + 1
      setBattlePrepRoundCount(newCount)
      if (newCount >= 12) {
        setTimeout(() => handleEndBattle(), 3000)
      }
    }
  }, [
    battlePrepRoundCount,
    chat.inputValue,
    handleEndBattle,
    interactionMode,
    isLiveCoachSession,
    outgoingMessageMetadata,
    scheduleGuidanceRefresh,
    selectedRoomType,
    sendChatMessage,
    trainingMode,
    trainingSessionId,
  ])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (chat.mentionQuery !== null && chat.mentionResults.length > 0) {
        e.preventDefault()
        chat.insertMention(chat.mentionResults[0])
        return
      }
      e.preventDefault()
      handleSend()
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    chat.handleInputChange(
      e,
      personaMap,
      chat.selectedRoom?.room.type,
      chat.selectedRoom?.room.persona_ids,
    )
  }

  const isBattlePrep = selectedRoomType === 'battle_prep' && !isTrainingSession
  const isVoiceBattlePrep = isTrainingModeBattlePrep(
    selectedRoomType,
    trainingMode,
    'voice',
    interactionMode,
    'turn_based',
  )
  const isVideoBattlePrep = isTrainingModeBattlePrep(
    selectedRoomType,
    trainingMode,
    'video',
    interactionMode,
    'turn_based',
  )
  const isRealtimeBattlePrep = isTrainingModeBattlePrep(
    selectedRoomType,
    trainingMode,
    'voice',
    interactionMode,
    'realtime',
  )
  const primaryPersona = roomPersonas[0]
  const roomCounterpartName = (chat.selectedRoom?.room.name || '').replace(/^备战[:：]\s*/, '').trim()
  const counterpartName = primaryPersona?.name || roomCounterpartName || tr('AI 面试官', 'AI Interviewer')
  const latestPersonaPrompt = React.useMemo(() => {
    const personaMessages = (selectedRoomMessages || []).filter(
      (m: { sender_type: string; content: string }) => m.sender_type === 'persona' && m.content.trim(),
    )
    return personaMessages[personaMessages.length - 1]?.content.trim() || ''
  }, [selectedRoomMessages])
  const latestGuidanceMessage = React.useMemo(() => {
    const messages = ((selectedRoomMessages || []) as ChatMessage[]).filter((message) => message.content.trim())
    return messages[messages.length - 1] || null
  }, [selectedRoomMessages])
  const scenarioTitleFromState = getStateStringValue(location.state, 'scenarioTitle')
  const scenarioDescriptionFromState = getStateStringValue(location.state, 'scenarioDescription')
  const scenarioCustomerProfileFromState = getStateStringValue(location.state, 'scenarioCustomerProfile')
  const scenarioOpeningLineFromState = getStateStringValue(location.state, 'scenarioOpeningLine')
  const scenarioPersonaRoleFromState = getStateStringValue(location.state, 'scenarioPersonaRole')
  const scenarioPersonaStyleFromState = getStateStringValue(location.state, 'scenarioPersonaStyle')
  const scenarioLearnerRoleFromState = getStateStringValue(location.state, 'scenarioLearnerRole')
  const scenarioTrainingPointsFromState = getStateStringArrayValue(location.state, 'scenarioTrainingPoints')
  const scenarioDifficultyFromState = getScenarioDifficultyFromState(location.state)
  const scenarioCategoryFromState = getScenarioCategoryFromState(location.state)
  const scenarioRequiredFromState = getStateBooleanValue(location.state, 'scenarioRequired')
  const scenarioPersonaRole = scenarioTrainingCard?.persona.role || scenarioPersonaRoleFromState
  const scenarioLearnerRole = scenarioTrainingCard?.learnerRole || scenarioLearnerRoleFromState
  const scenarioCategory = scenarioTrainingCard?.category || scenarioCategoryFromState
  const scenarioDifficulty = scenarioTrainingCard?.difficulty || scenarioDifficultyFromState
  const scenarioRequired = scenarioTrainingCard ? scenarioTrainingCard.required : scenarioRequiredFromState
  const scenarioTrainingPoints = scenarioTrainingCard?.trainingPoints.length
    ? scenarioTrainingCard.trainingPoints
    : scenarioTrainingPointsFromState
  const trainingBackPath = scenarioTrainingId ? APP_ROUTES.practiceScenarios : APP_ROUTES.practiceCustom
  const trainingContextTitle = scenarioTrainingCard?.title
    || scenarioTitleFromState
    || chat.selectedRoom?.room.name
    || tr('训练会话', 'Training session')
  const trainingContextSubtitle = hasScenarioTrainingContext
    ? compactStrings([
      scenarioPersonaRole,
      scenarioLearnerRole ? `${tr('你扮演', 'You play')}: ${scenarioLearnerRole}` : null,
    ]).join(' · ')
    : compactStrings([
      counterpartName,
      trainingMode ? getTrainingModeLabel(trainingMode, tr) : null,
      getInteractionModeLabel(interactionMode, tr),
    ]).join(' · ')
  const trainingContextTags = compactTags([
    scenarioCategory ? { label: getScenarioCategoryLabel(scenarioCategory, tr), tone: 'category' } : null,
    scenarioDifficulty ? { label: getScenarioDifficultyLabel(scenarioDifficulty, tr), tone: 'difficulty' } : null,
    scenarioRequired === true
      ? { label: tr('必练', 'Required'), tone: 'required' }
      : scenarioRequired === false
        ? { label: tr('选练', 'Optional'), tone: 'optional' }
        : null,
    trainingMode ? { label: getTrainingModeLabel(trainingMode, tr), tone: 'mode' } : null,
    { label: getInteractionModeLabel(interactionMode, tr), tone: 'mode' },
  ])
  const trainingContextDescription = scenarioTrainingCard?.description
    || scenarioDescriptionFromState
    || scenarioOpeningLineFromState
    || tr('本轮训练已连接 AI 陪练，完成对话后可结束练习并生成复盘。', 'This training session is connected to an AI coach. End the practice when you are ready for review.')
  const trainingContextOpeningLine = scenarioTrainingCard?.openingLine || scenarioOpeningLineFromState
  const trainingContextCustomerProfile = scenarioTrainingCard?.customerProfile || scenarioCustomerProfileFromState
  const trainingContextPersonaStyle = scenarioTrainingCard?.persona.style || scenarioPersonaStyleFromState
  const trainingContextPoints = scenarioTrainingPoints.slice(0, 3).join(' / ')
  const trainingInputPlaceholder = scenarioCategory === 'sales' || scenarioCategory === 'customer_service'
    ? tr('输入你想对客户说的话，Enter 发送', 'Type what you want to say to the customer. Enter to send')
    : tr('输入你的回应，Enter 发送', 'Type your response. Enter to send')

  const liveCoachLanguageSummary = compactStrings([
    sourceLanguageLabel || liveCoachLanguagePair.sourceLanguage,
    targetLanguageLabel || liveCoachLanguagePair.targetLanguage,
  ]).join(' -> ')
  const resolvedTrainingBackPath = isLiveCoachSession ? APP_ROUTES.practiceLiveCoach : trainingBackPath
  const resolvedTrainingContextTitle = isLiveCoachSession ? tr('实时教练', 'Live coach') : trainingContextTitle
  const resolvedTrainingContextSubtitle = isLiveCoachSession
    ? compactStrings([
      tr('真实对话', 'Real conversation'),
      liveCoachLanguageSummary || null,
      getInteractionModeLabel(interactionMode, tr),
    ]).join(' / ')
    : trainingContextSubtitle
  const resolvedTrainingContextTags = isLiveCoachSession
    ? compactTags([
      { label: tr('实时教练', 'Live coach'), tone: 'live' },
      sourceLanguageLabel ? { label: sourceLanguageLabel, tone: 'live' } : null,
      targetLanguageLabel ? { label: targetLanguageLabel, tone: 'live' } : null,
      { label: getInteractionModeLabel(interactionMode, tr), tone: 'mode' },
    ])
    : trainingContextTags
  const resolvedTrainingContextDescription = isLiveCoachSession
    ? tr('私人 AI 教练已连接实时转写和复盘流程。', 'Private AI coaching is connected to the live transcript and review loop.')
    : trainingContextDescription
  const resolvedTrainingContextCustomerProfile = isLiveCoachSession ? null : trainingContextCustomerProfile
  const resolvedTrainingContextPersonaStyle = isLiveCoachSession ? null : trainingContextPersonaStyle
  const resolvedTrainingContextOpeningLine = isLiveCoachSession ? null : trainingContextOpeningLine
  const resolvedTrainingContextPoints = isLiveCoachSession ? null : trainingContextPoints
  const resolvedTrainingInputPlaceholder = isLiveCoachSession
    ? tr('输入会议现场内容或你的下一句，回车发送', 'Type a meeting line or your next reply. Enter to send')
    : trainingInputPlaceholder
  const guidanceBarTitle = isLiveCoachSession ? tr('实时教练', 'Live coach') : tr('实时指导', 'Realtime guidance')
  const guidanceReadyText = isLiveCoachSession
    ? tr('已准备好为这场对话提供教练建议', 'Ready to coach this conversation')
    : tr('本次训练中可用', 'Ready during this training session')
  const guidanceStreamingText = isLiveCoachSession
    ? tr('正在观察实时转写', 'Watching the live transcript')
    : tr('本次训练中正在流式输出', 'Streaming during this training session')
  const guidanceActionText = isLiveCoachSession ? tr('问教练', 'Ask coach') : tr('给我指导', 'Guide me')
  const realtimeBarTitle = isLiveCoachSession
    ? tr('真实对话教练', 'Live conversation coach')
    : tr('实时语音训练', 'Realtime voice practice')
  const realtimeBarCopy = isLiveCoachSession
    ? liveCoachLanguageSummary || tr('实时通道已绑定真实对话教练', 'Realtime channel is bound to live coaching')
    : latestPersonaPrompt || tr('实时通道已绑定当前训练房间', 'Realtime channel is bound to this training room')

  useEffect(() => {
    if (!trainingSessionId || !latestGuidanceMessage || latestGuidanceMessage.sender_type !== 'persona') return
    const messageKey = `${selectedRoomId || 'room'}:${latestGuidanceMessage.id}`
    if (lastAutoGuidanceMessageKeyRef.current === messageKey) return
    lastAutoGuidanceMessageKeyRef.current = messageKey
    scheduleGuidanceRefresh({
      autoOpenOnSignal: true,
      minIntervalMs: GUIDANCE_AUTO_MIN_INTERVAL_MS,
    })
  }, [
    latestGuidanceMessage,
    scheduleGuidanceRefresh,
    selectedRoomId,
    trainingSessionId,
  ])

  useEffect(() => {
    if (!isVoiceBattlePrep || !selectedRoomId) {
      if (!isVoiceBattlePrep) {
        preparedVoiceRoomRef.current = null
        setLastVoiceTranscript(null)
        setVoiceRecorderState('idle')
        setVoiceRecorderError(null)
      }
      return
    }
    if (preparedVoiceRoomRef.current === selectedRoomId) return
    voice.prepareVoiceSession()
    preparedVoiceRoomRef.current = selectedRoomId
  }, [isVoiceBattlePrep, selectedRoomId, voice])

  useEffect(() => {
    if (!isVideoBattlePrep) {
      setLastVideoAnswerAt(null)
      setVideoAnswerStatus('idle')
      setVideoAnswerError(null)
      setVideoRecorderOpen(false)
    }
  }, [isVideoBattlePrep])

  const voicePracticeStatus = voice.playingPersonaId
    ? tr('AI 正在语音回应', 'AI is speaking')
    : chat.typingPersona
      ? tr('AI 正在组织回应', 'AI is preparing a reply')
      : voiceRecorderError
        ? voiceRecorderError
        : voice.voiceError
        ? voice.voiceError
        : voiceRecorderState === 'recording'
          ? tr('正在聆听你的回答', 'Listening to your answer')
          : voiceRecorderState === 'processing'
            ? tr('正在识别你的语音', 'Recognizing your voice')
            : lastVoiceTranscript
              ? tr('语音轮次已发送', 'Voice turn sent')
              : voice.voiceEnabled && !voice.voiceMuted
                ? tr('语音已就绪', 'Voice ready')
                : voice.voiceMuted
                  ? tr('语音已静音', 'Voice muted')
                  : tr('语音未开启', 'Voice off')

  const voicePracticeActionLabel = voice.voiceEnabled && !voice.voiceMuted
    ? tr('静音', 'Mute')
    : tr('开启语音', 'Enable voice')

  const handleVoicePracticeAction = () => {
    if (voice.voiceEnabled && !voice.voiceMuted) {
      voice.toggleVoice()
      return
    }
    voice.prepareVoiceSession()
  }

  const handleVoiceRecorderStateChange = React.useCallback((
    state: VoiceRecorderState,
    error: string | null,
  ) => {
    setVoiceRecorderState(state)
    setVoiceRecorderError(error)
    if (state === 'recording' || state === 'processing') {
      setLastVoiceTranscript(null)
    }
  }, [])

  const handleRealtimeTranscriptPersisted = React.useCallback((text: string, role: 'user' | 'assistant' = 'user') => {
    const transcript = text.trim()
    if (!transcript) return
    setLastVoiceTranscript(transcript)
    scheduleGuidanceRefresh({
      extraTurn: {
        speaker: role === 'assistant' ? 'counterpart' : 'user',
        text: transcript,
        metadata: {
          ...(liveCoachRealtimeTranscriptMetadata || {}),
          source: isLiveCoachSession ? 'live_coach_realtime_voice' : 'realtime_voice',
          trainingMode: 'voice',
          interactionMode: 'realtime',
          trainingProfile,
          realtimeRole: role,
        },
      },
      autoOpenOnSignal: true,
      minIntervalMs: GUIDANCE_AUTO_MIN_INTERVAL_MS,
    })
    setTimeout(chat.scrollToBottom, 100)
  }, [
    chat.scrollToBottom,
    isLiveCoachSession,
    liveCoachRealtimeTranscriptMetadata,
    scheduleGuidanceRefresh,
    trainingProfile,
  ])

  const handleCompleteTrainingSession = React.useCallback(async () => {
    if (!trainingSessionId || trainingSessionCompleting) return
    const hasMessages = (selectedRoomMessages || []).some((message: { content?: string }) => (
      typeof message.content === 'string' && message.content.trim().length > 0
    ))
    setTrainingSessionCompleting(true)
    try {
      if (isLiveCoachSession && guidanceEvents.length > 0) {
        const signature = guidanceEventsSignature(guidanceEvents)
        if (persistedGuidanceSignatureRef.current !== signature) {
          try {
            await persistTrainingGuidanceEvents(trainingSessionId, {
              events: guidanceEvents,
              reason: 'session_complete',
              source: 'client',
              window_size: guidanceTurnsRef.current.length,
              total_turn_count: guidanceTurnsRef.current.length,
              metadata: {
                ...(liveCoachGuidanceMetadata || {}),
                trainingMode,
                interactionMode,
                trainingProfile,
              },
            })
            persistedGuidanceSignatureRef.current = signature
          } catch (saveError: unknown) {
            setGuidanceOpen(true)
            setGuidanceError(
              saveError instanceof Error
                ? saveError.message
                : tr('会话教练建议未能保存', 'Coach events could not be saved'),
            )
          }
        }
      }
      const completionBranchMetadata = buildTrainingCompletionBranchMetadata(messageTreeSelection)
      const session = await completeTrainingSession(trainingSessionId, {
        generate_report: hasMessages,
        ...(completionBranchMetadata ? { metadata: completionBranchMetadata } : {}),
      })
      setTrainingSessionCompleted(true)
      const reportId = Number(session.report_id)
      const scenarioScore = Number.isFinite(reportId) && reportId > 0
        ? await getTrainingSessionReport(trainingSessionId)
          .then(extractTrainingReportScore)
          .catch(() => undefined)
        : undefined
      if (hasMessages && scenarioTrainingId) {
        saveScenarioTrainingProgress(
          markScenarioTrainingCompleted(getScenarioTrainingProgress(progressScope), scenarioTrainingId, {
            trainingSessionId: session.session_id || trainingSessionId,
            reportId: session.report_id,
            scoreId: session.score_id,
            score: scenarioScore,
            scoreStatus: scenarioScore === undefined ? 'pending' : 'ready',
            scope: progressScope,
            completedAt: session.completed_at ?? undefined,
          }),
          progressScope,
        )
      }
      if (Number.isFinite(reportId) && reportId > 0) {
        await analysis.openReport(reportId)
      } else if (hasMessages) {
        await analysis.handleAnalyze()
      } else {
        navigate(resolvedTrainingBackPath)
      }
    } catch (e: unknown) {
      alert(getErrorMessage(e, tr('训练完成失败', 'Failed to complete training session')))
    } finally {
      setTrainingSessionCompleting(false)
    }
  }, [
    analysis,
    guidanceEvents,
    interactionMode,
    isLiveCoachSession,
    liveCoachGuidanceMetadata,
    messageTreeSelection,
    navigate,
    progressScope,
    resolvedTrainingBackPath,
    scenarioTrainingId,
    selectedRoomMessages,
    trainingMode,
    trainingProfile,
    trainingSessionCompleting,
    trainingSessionId,
    tr,
  ])

  const handleRequestGuidance = React.useCallback(async () => {
    if (guidanceLoading) return
    await refreshGuidance({ open: true })
  }, [guidanceLoading, refreshGuidance])

  const videoAnswerCount = React.useMemo(() => {
    if (!isVideoBattlePrep || !selectedRoomMessages) return 0
    return selectedRoomMessages.filter((m: { sender_type: string; content: string }) => (
      m.sender_type === 'user' && m.content.includes('[video-answer]')
    )).length
  }, [isVideoBattlePrep, selectedRoomMessages])

  const videoPracticeStatus = chat.typingPersona
    ? tr('AI 正在根据你的视频回答组织追问', 'AI is preparing a follow-up from your video answer')
    : videoAnswerStatus === 'uploading'
      ? tr('正在上传视频回答', 'Uploading video answer')
      : videoAnswerStatus === 'error'
        ? videoAnswerError || tr('视频提交失败，请重试', 'Video submission failed. Please try again')
        : lastVideoAnswerAt || videoAnswerStatus === 'sent'
      ? tr('视频回答已提交，正在进入追问或复盘流程', 'Video answer submitted; continuing into follow-up or review')
      : videoAnswerCount > 0
        ? tr('已提交 {count} 段视频回答', '{count} video answers submitted', { count: videoAnswerCount })
        : tr('点击输入区的视频按钮后再打开摄像头录制', 'Use the video button in the input area, then open the camera to record')
  const aiIsActive = Boolean(voice.playingPersonaId || chat.typingPersona)
  const userIsActive = voiceRecorderState === 'recording' || voiceRecorderState === 'processing' || videoAnswerStatus === 'uploading'
  const voicePrompt = latestPersonaPrompt || voicePracticeStatus
  const videoWorkspacePrompt = latestPersonaPrompt || (
    isVideoBattlePrep
      ? videoPracticeStatus
      : tr('录制一段视频回答并发送到当前对话。', 'Record a video answer and send it to this conversation.')
  )
  const messageTreeTailNode = messageTreeSelection
    ? messageTreeSelection.path[messageTreeSelection.path.length - 1] ?? null
    : null
  const messageTreeSelectedNode = messageTreeSelection
    ? messageTreeSelection.path.find((item) => item.publicId === messageTreeSelection.selectedMessageId) ?? null
    : null
  const messageTreeForkPoint = messageTreeSelection
    ? findMessageTreeForkPoint(messageTreeSelection.path)
    : null
  const messageTreeSelectedLabel = messageTreeSelectedNode
    ? compactTreeNodeContent(messageTreeSelectedNode, messageTreeSelectedNode.publicId)
    : messageTreeSelection?.selectedMessageId ?? null
  const messageTreeTailLabel = messageTreeTailNode
    ? compactTreeNodeContent(messageTreeTailNode, messageTreeTailNode.publicId)
    : null
  const messageTreeForkPointLabel = messageTreeForkPoint
    ? compactTreeNodeContent(messageTreeForkPoint, messageTreeForkPoint.publicId)
    : null

  const handleVideoRecorded = React.useCallback(async (result: VideoAnswerResult) => {
    setVideoRecorderOpen(false)
    if (isVideoBattlePrep) {
      setVideoAnswerStatus('uploading')
      setVideoAnswerError(null)
    }
    const fallbackCaption = isVideoBattlePrep
      ? tr('我提交了一段视频回答，请继续追问或总结。', 'I submitted a recorded video answer. Please continue with a follow-up or summary.')
      : undefined
    if (!trainingSessionId || selectedRoomId == null) {
      if (isVideoBattlePrep) {
        setVideoAnswerStatus('error')
        setVideoAnswerError(
          tr('视频回答需要已绑定的训练会话和房间信息。', 'Video answers require a bound training session and room.'),
        )
      }
      return
    }
    let videoUrl = result.url
    let videoSize = result.size
    try {
      const uploaded = await uploadVideoAnswer(result.blob, {
        trainingSessionId,
        roomId: selectedRoomId,
      })
      videoUrl = uploaded.url
      videoSize = uploaded.size
    } catch (error) {
      console.error('Video upload failed:', error)
      if (isVideoBattlePrep) {
        setVideoAnswerStatus('error')
        setVideoAnswerError(error instanceof Error ? error.message : tr('视频上传失败', 'Video upload failed'))
        return
      }
    }
    const sent = await chat.sendVideoAnswer({
      url: videoUrl,
      mimeType: result.mimeType,
      title: tr('视频回答', 'Video answer'),
      durationMs: result.durationMs,
      size: videoSize,
      recordedAt: result.recordedAt,
      trainingEvent: isVideoBattlePrep ? {
        type: 'video_answer_submitted',
        trainingMode: 'video',
        schemaVersion: 1,
        reportDimensions: ['content_delivery', 'camera_presence'],
        cameraPresenceStatus: 'placeholder',
      } : undefined,
    }, chat.inputValue.trim() || fallbackCaption)
    if (sent && isVideoBattlePrep) {
      setVideoAnswerStatus('sent')
      setLastVideoAnswerAt(result.recordedAt)
      scheduleGuidanceRefresh({
        extraTurn: {
          speaker: 'user',
          text: chat.inputValue.trim() || fallbackCaption || tr('我提交了一段视频回答。', 'I submitted a recorded video answer.'),
          metadata: {
            source: 'video_answer',
            mimeType: result.mimeType,
            durationMs: result.durationMs,
            trainingMode: 'video',
            interactionMode: 'turn_based',
          },
        },
        autoOpenOnSignal: true,
        minIntervalMs: GUIDANCE_AUTO_MIN_INTERVAL_MS,
      })
    } else if (isVideoBattlePrep) {
      setVideoAnswerStatus('error')
      setVideoAnswerError(tr('视频消息发送失败', 'Video message failed to send'))
    }
  }, [chat, isVideoBattlePrep, scheduleGuidanceRefresh, tr])

  return (
    <>
      <div className={`chat-page-center${isTrainingSession ? ' training-session' : ''}`}>
      {/* Chat header */}
      <div className="chat-page-header">
        <div className="chat-page-header-left">
          <button
            className="chat-page-back-btn"
            onClick={() => navigate(APP_ROUTES.conversations)}
            title={tr('返回对话库', 'Back to conversation library')}
          >
            <ArrowLeft size={18} />
          </button>
          <h3>{chat.selectedRoom?.room.name ?? ''}</h3>
          {chat.selectedRoom && (
            <span className={`room-type-badge ${chat.selectedRoom.room.type}`}>
              {chat.selectedRoom.room.type === 'private'
                ? tr('私聊', 'Private')
                : chat.selectedRoom.room.type === 'group'
                  ? tr('群聊', 'Group')
                  : tr('备战', 'Battle prep')}
            </span>
          )}
        </div>
        <div className="chat-page-header-actions">
          <button
            className={`header-action-btn ${showEmotionSidebar ? 'active' : ''}`}
            onClick={() => setShowEmotionSidebar((v) => !v)}
            title={tr('实时情绪面板', 'Live emotion panel')}
          >
            <Activity size={16} />
          </button>
          <button
            className="header-action-btn"
            onClick={() => setShowEmotionCurve(true)}
            title={tr('情绪详细分析', 'Detailed emotion analysis')}
          >
            <BarChart3 size={16} />
          </button>
          <button
            className="header-action-btn"
            onClick={analysis.handleAnalyze}
            title={tr('分析', 'Analyze')}
            disabled={analysis.analyzingRoom}
          >
            <BarChart2 size={16} />
          </button>
          <button
            className="header-action-btn coaching"
            onClick={() => coaching.handleStartCoaching()}
            title={tr('AI 复盘', 'AI Review')}
            disabled={coaching.coachingSending}
          >
            <GraduationCap size={16} />
          </button>
          <div className="export-dropdown-wrapper">
            <button
              className="header-action-btn"
              onClick={() => setShowExportMenu((v) => !v)}
              title={tr('导出', 'Export')}
            >
              <Download size={16} />
            </button>
            {showExportMenu && (
              <div className="export-menu">
                <div
                  className="export-menu-item"
                  onClick={() => {
                    setShowExportMenu(false)
                    exportRoomHtml(chat.selectedRoom!.room.id).catch(console.error)
                  }}
                >
                  <FileText size={15} />
                  <div>
                    <div>{tr('HTML 格式', 'HTML format')}</div>
                    <span className="export-menu-desc">{tr('保留聊天样式', 'Preserves chat styling')}</span>
                  </div>
                </div>
                <div
                  className="export-menu-item"
                  onClick={() => {
                    setShowExportMenu(false)
                    exportRoom(chat.selectedRoom!.room.id).catch(console.error)
                  }}
                >
                  <FileDown size={15} />
                  <div>
                    <div>{tr('Markdown 格式', 'Markdown format')}</div>
                    <span className="export-menu-desc">{tr('纯文本，便于编辑', 'Plain text, easy to edit')}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {isTrainingSession && (
        <section className="chat-page-training-banner" data-testid="training-context-banner">
          <div className="chat-page-training-top">
            <button
              className="chat-page-training-back"
              type="button"
              onClick={() => navigate(resolvedTrainingBackPath)}
            >
              <ArrowLeft size={15} />
              {tr('返回', 'Back')}
            </button>

            <div className="chat-page-training-copy">
              <strong>{resolvedTrainingContextTitle}</strong>
              {resolvedTrainingContextSubtitle && <span>{resolvedTrainingContextSubtitle}</span>}
              <div className="chat-page-training-tags" aria-label={tr('练习标签', 'Practice tags')}>
                {resolvedTrainingContextTags.map((tag) => (
                  <span className={tag.tone ? `tone-${tag.tone}` : undefined} key={`${tag.tone || 'tag'}:${tag.label}`}>
                    {tag.label}
                  </span>
                ))}
              </div>
              <button
                className={`chat-page-training-details-toggle${trainingSceneExpanded ? ' expanded' : ''}`}
                type="button"
                aria-expanded={trainingSceneExpanded}
                aria-controls="training-scene-details"
                onClick={() => setTrainingSceneExpanded((v) => !v)}
              >
                <span>{trainingSceneExpanded ? tr('收起', 'Hide details') : tr('详情', 'Details')}</span>
                <ChevronDown size={14} />
              </button>
            </div>

            <button
              className={`chat-page-training-complete${trainingSessionCompleted ? ' completed' : ''}`}
              type="button"
              onClick={handleCompleteTrainingSession}
              disabled={trainingSessionCompleting || analysis.analyzingRoom}
            >
              {trainingSessionCompleting ? <Loader2 size={15} className="spin" /> : <CheckCircle2 size={15} />}
              {trainingSessionCompleted ? tr('已结束', 'Ended') : tr('结束练习', 'End practice')}
            </button>
          </div>

          {llmModelChoices.length > 0 && (
            <div
              className="chat-page-llm-selector"
              data-testid="training-llm-selector"
              aria-label={t('training.llm.selectorLabel')}
            >
              <span className="chat-page-llm-selector-title">{t('training.llm.selectorLabel')}</span>
              <label>
                <span>{t('training.llm.provider')}</span>
                <select
                  aria-label={t('training.llm.providerAria')}
                  value={selectedLlmProvider}
                  onChange={handleLlmProviderChange}
                  disabled={chat.sending}
                >
                  {llmProviderOptions.map((provider) => (
                    <option key={provider.provider} value={provider.provider}>
                      {provider.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t('training.llm.model')}</span>
                <select
                  aria-label={t('training.llm.modelAria')}
                  value={selectedLlmChoice?.key
                    ?? selectedProviderModelChoices.find(isLlmModelChoiceSelectable)?.key
                    ?? selectedProviderModelChoices[0]?.key
                    ?? ''}
                  onChange={handleLlmModelChange}
                  disabled={chat.sending}
                >
                  {selectedProviderModelChoices.map((choice) => (
                    <option key={choice.key} value={choice.key} disabled={choice.disabled}>
                      {formatLlmOptionLabel(choice, t)}
                    </option>
                  ))}
                </select>
              </label>
              <div
                className="chat-page-llm-details"
                aria-label={t('training.llm.detailsAria')}
              >
                {displayedLlmChoice?.description && (
                  <span className="chat-page-llm-description" title={displayedLlmChoice.description}>
                    {displayedLlmChoice.description}
                  </span>
                )}
                {llmDetailTags.length > 0 && (
                  <span className="chat-page-llm-tags">
                    {llmDetailTags.map((tag) => (
                      <span
                        key={tag.key}
                        className={tag.tone === 'warning' ? 'warning' : undefined}
                      >
                        {tag.label}
                      </span>
                    ))}
                  </span>
                )}
              </div>
            </div>
          )}

          <div
            id="training-scene-details"
            className={`chat-page-training-scene${trainingSceneExpanded ? ' expanded' : ' collapsed'}`}
          >
            {resolvedTrainingContextCustomerProfile && (
              <p>
                <strong>{tr('客户画像', 'Customer profile')}:</strong>
                <span>{resolvedTrainingContextCustomerProfile}</span>
              </p>
            )}
            <p>
              <strong>{tr('场景描述', 'Scenario')}:</strong>
              <span>{resolvedTrainingContextDescription}</span>
            </p>
            {resolvedTrainingContextPersonaStyle && (
              <p>
                <strong>{tr('角色状态', 'Persona stance')}:</strong>
                <span>{resolvedTrainingContextPersonaStyle}</span>
              </p>
            )}
            {resolvedTrainingContextOpeningLine && resolvedTrainingContextOpeningLine !== resolvedTrainingContextDescription && (
              <p>
                <strong>{tr('客户开场', 'Opening line')}:</strong>
                <span>{resolvedTrainingContextOpeningLine}</span>
              </p>
            )}
            {resolvedTrainingContextPoints && (
              <p>
                <strong>{tr('练习重点', 'Focus')}:</strong>
                <span>{resolvedTrainingContextPoints}</span>
              </p>
            )}
          </div>
        </section>
      )}

      {trainingSessionId && (
        <section className="chat-page-guidance-bar" data-testid="training-guidance-bar">
          <div className="guidance-copy">
            <Lightbulb size={15} />
            <strong>{guidanceBarTitle}</strong>
            <span>
              {guidanceError
                ? guidanceError
                : localizedGuidanceEvents[0]?.displayMessage || (
                  guidanceStreamConnected
                    ? guidanceStreamingText
                    : guidanceReadyText
                )}
            </span>
          </div>
          <button
            className="guidance-action"
            type="button"
            onClick={handleRequestGuidance}
            disabled={guidanceLoading}
          >
            {guidanceLoading ? <Loader2 size={14} className="spin" /> : <Lightbulb size={14} />}
            {guidanceLoading ? tr('思考中', 'Thinking') : guidanceActionText}
          </button>
        </section>
      )}

      {trainingSessionId && isLiveCoachSession && (
        <section className="chat-page-live-coach-strip" data-testid="live-coach-language-strip">
          <div className="live-coach-strip-main">
            <Languages size={15} />
            <strong>{liveCoachLanguageSummary || tr('双语辅助', 'Bilingual assist')}</strong>
            <span>{tr('转写、下一句和复盘语言按本场配置。', 'Transcript, next-line guidance, and review language follow this session.')}</span>
          </div>
        </section>
      )}

      {trainingSessionId && guidanceOpen && (
        <section className="chat-page-guidance-panel" data-testid="training-guidance-panel">
          <div className="guidance-panel-header">
            <strong>{isLiveCoachSession ? tr('实时教练', 'Live coach') : tr('实时指导', 'Realtime guidance')}</strong>
            <button
              type="button"
              onClick={() => setGuidanceOpen(false)}
              title={tr('关闭指导', 'Close guidance')}
              aria-label={tr('关闭指导', 'Close guidance')}
            >
              <X size={14} />
            </button>
          </div>
          {guidanceLoading && guidanceEvents.length === 0 && (
            <div className="guidance-empty">{tr('正在读取最新一轮对话', 'Reading the latest turn')}</div>
          )}
          {!guidanceLoading && guidanceEvents.length === 0 && !guidanceError && (
            <div className="guidance-empty">{tr('暂无指导', 'No guidance yet')}</div>
          )}
          {guidanceError && (
            <div className="guidance-error">{guidanceError}</div>
          )}
          {guidanceEvents.length > 0 && (
            <div className="guidance-event-list">
              {localizedGuidanceEvents.map((event, index) => (
                <article
                  className={`guidance-card ${event.severity || 'info'}`}
                  key={`${event.event_type}-${index}`}
                >
                  <div className="guidance-card-header">
                    <span>{event.displayTitle}</span>
                    <small>{event.displayType}</small>
                  </div>
                  <p>{event.displayMessage}</p>
                  {event.displaySuggestedText && <blockquote>{event.displaySuggestedText}</blockquote>}
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {messageTreeSelection && (
        <section className="chat-page-message-tree-strip" aria-label={t('messageTree.current.aria')}>
          <div className="message-tree-strip-copy">
            <ListTree size={15} />
            <strong>{t('messageTree.current.title')}</strong>
            <span>
              {t('messageTree.current.summary', {
                count: messageTreeSelection.path.length,
                branch: messageTreeSelection.branchId || t('messageTree.actions.noBranch'),
              })}
            </span>
            <em>{t('messageTree.actions.controlledBadge')}</em>
          </div>
          <div className="message-tree-strip-path">
            <Route size={14} />
            {messageTreeSelection.path.map((item, index) => (
              <span
                key={item.publicId}
                className={item.publicId === messageTreeSelection.selectedMessageId ? 'active' : undefined}
                title={compactTreeNodeContent(item, item.publicId)}
              >
                {index + 1}. {compactTreeNodeContent(item, item.publicId)}
              </span>
            ))}
          </div>
          <div className="message-tree-strip-details">
            <span>
              <strong>{t('messageTree.actions.currentSelection')}</strong>
              <em title={messageTreeSelectedLabel ?? undefined}>
                {messageTreeSelectedLabel ?? t('messageTree.actions.noPath')}
              </em>
            </span>
            <span>
              <strong>{t('messageTree.actions.tailNode')}</strong>
              <em title={messageTreeTailLabel ?? undefined}>
                {messageTreeTailLabel ?? t('messageTree.actions.noPath')}
              </em>
            </span>
            <span>
              <strong>{t('messageTree.actions.forkPoint')}</strong>
              <em title={messageTreeForkPointLabel ?? undefined}>
                {messageTreeForkPointLabel ?? t('messageTree.actions.noForkPoint')}
              </em>
            </span>
          </div>
          <button
            type="button"
            onClick={() => setMessageTreeSelection(null)}
            title={t('messageTree.current.clear')}
            aria-label={t('messageTree.current.clear')}
          >
            <X size={14} />
          </button>
        </section>
      )}

      {/* Battle prep bar */}
      {isBattlePrep && (
        <div className="chat-page-battle-bar">
          <Zap size={14} />
          <span>{tr('备战模式 · 第 {count}/12 轮', 'Battle prep · Round {count}/12', { count: battlePrepRoundCount })}</span>
          <div className="battle-progress">
            <div
              className="battle-progress-fill"
              style={{ width: `${(battlePrepRoundCount / 12) * 100}%` }}
            />
          </div>
          <button
            className="end-battle-btn"
            onClick={handleEndBattle}
            disabled={battlePrepEnding}
          >
            {battlePrepEnding ? (
              <Loader2 size={14} className="spin" />
            ) : (
              <Flag size={14} />
            )}
            {battlePrepEnding ? tr('生成话术纸条...', 'Generating cheat sheet...') : tr('结束备战', 'End Battle Prep')}
          </button>
        </div>
      )}

      {isVoiceBattlePrep && (
        <div className="chat-page-voice-call-bar" data-testid="voice-practice-bar">
          <PhoneCall size={15} />
          <div className="voice-call-copy">
            <strong>{tr('电话式练习', 'Phone-style practice')}</strong>
            <span>{voicePracticeStatus}</span>
          </div>
          <button
            className="voice-call-action"
            type="button"
            onClick={handleVoicePracticeAction}
          >
            {voice.voiceEnabled && !voice.voiceMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            {voicePracticeActionLabel}
          </button>
        </div>
      )}

      {isRealtimeBattlePrep && (
        <div
          className={`chat-page-realtime-call-bar${isLiveCoachSession ? ' live-coach' : ''}`}
          data-testid="realtime-practice-bar"
          data-training-profile={trainingProfile}
        >
          <Radio size={15} />
          <div className="realtime-call-copy">
            <strong>{realtimeBarTitle}</strong>
            <span>{realtimeBarCopy}</span>
          </div>
          <RealtimeVoiceRecorder
            key={`${trainingSessionId || 'no-session'}:${selectedRoomId || 'no-room'}`}
            roomId={selectedRoomId}
            trainingSessionId={trainingSessionId}
            disabled={chat.sending}
            personaId={primaryPersona?.id || null}
            counterpartName={counterpartName}
            transcriptMetadata={liveCoachRealtimeTranscriptMetadata}
            onPersistedTranscript={handleRealtimeTranscriptPersisted}
          />
        </div>
      )}

      {isVideoBattlePrep && (
        <div className="chat-page-video-answer-bar" data-testid="video-practice-bar">
          <Video size={15} />
          <div className="video-answer-copy">
            <strong>{tr('视频回答训练', 'Video answer practice')}</strong>
            <span>{videoPracticeStatus}</span>
          </div>
        </div>
      )}

      {/* Chat body: messages + optional emotion sidebar */}
      <div className="chat-page-chat-with-sidebar">
        {videoRecorderOpen && (
          <section className="chat-page-video-recorder-overlay" data-testid="video-recorder-workspace">
            <div className="video-workspace-header">
              <div>
                <strong>{tr('视频回答', 'Video answer')}</strong>
                <span>{videoWorkspacePrompt}</span>
              </div>
              <button
                type="button"
                onClick={() => setVideoRecorderOpen(false)}
                title={tr('关闭视频录制器', 'Close video recorder')}
              >
                <X size={18} />
              </button>
            </div>
            <div className="video-workspace-body">
              <div className="video-workspace-context">
                <div
                  className="video-workspace-avatar"
                  style={{ background: primaryPersona?.avatar_color || '#0F766E' }}
                >
                  {displayInitial(counterpartName)}
                </div>
                <div>
                  <strong>{counterpartName}</strong>
                  <span>{tr('等待你的视频回答', 'Waiting for your video answer')}</span>
                </div>
              </div>
              <VideoAnswerRecorder
                disabled={chat.sending}
                onCancel={() => setVideoRecorderOpen(false)}
                onRecorded={handleVideoRecorded}
              />
            </div>
          </section>
        )}

        <div className="chat-page-chat-column">
          {isVoiceBattlePrep && (
            <section className="training-voice-panel" data-testid="training-voice-panel">
              <div className="training-voice-persona">
                <div
                  className="training-voice-avatar"
                  style={{ background: primaryPersona?.avatar_color || '#0F766E' }}
                >
                  {displayInitial(counterpartName)}
                </div>
                <div className="training-voice-copy">
                  <strong>{counterpartName}</strong>
                  <span>{aiIsActive ? tr('AI 正在回应', 'AI is responding') : tr('电话式练习已就绪', 'Phone-style practice ready')}</span>
                </div>
              </div>
              <div className="training-voice-current">
                <div className={`training-voice-wave ${userIsActive ? 'listening' : aiIsActive ? 'speaking' : ''}`}>
                  {Array.from({ length: 21 }, (_, i) => (
                    <span
                      key={i}
                      style={{
                        height: `${8 + ((i * 7) % 24)}px`,
                        animationDelay: `${i * 38}ms`,
                      }}
                    />
                  ))}
                </div>
                <p>{voicePrompt}</p>
              </div>
            </section>
          )}

          <MessageList
            messages={chat.selectedRoom?.messages ?? []}
            streamingEntries={chat.streamingEntries}
            highlightedMessageId={analysis.highlightedMessageId}
            personaMap={personaMap}
            listRef={chat.messageListRef}
            dispatchSummary={chat.dispatchSummary}
            dispatchExpanded={chat.dispatchExpanded}
            onToggleDispatch={() => chat.setDispatchExpanded((v) => !v)}
            typingPersona={chat.typingPersona}
            playingPersonaId={voice.playingPersonaId}
            currentTreeSelection={messageTreeSelection}
            onSelectTreePath={setMessageTreeSelection}
            onClick={() => showExportMenu && setShowExportMenu(false)}
          />

          {/* Mobile pill buttons above input */}
          <div className="chat-mobile-pills">
            {[
              { key: 'cheatsheet', label: tr('锦囊', 'Tips') },
              { key: 'coaching', label: tr('教练', 'Coach') },
              { key: 'analysis', label: tr('评分', 'Score') },
              { key: 'emotion', label: tr('情绪', 'Emotion') },
            ].map((pill) => (
              <button
                key={pill.key}
                className={`chat-mobile-pill-btn${mobileSheet === pill.key ? ' active' : ''}`}
                onClick={() => setMobileSheet(mobileSheet === pill.key ? null : pill.key)}
              >
                {pill.label}
              </button>
            ))}
          </div>

          <ChatInput
            value={chat.inputValue}
            onInputChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onSend={handleSend}
            sending={chat.sending}
            placeholder={
              isTrainingSession
                ? resolvedTrainingInputPlaceholder
                : chat.selectedRoom?.room.type === 'group'
                ? tr('输入消息... 使用 @ 提及角色', 'Type a message... use @ to mention personas')
                : tr('输入消息...', 'Type a message...')
            }
            mentionQuery={chat.mentionQuery}
            mentionResults={chat.mentionResults}
            onInsertMention={chat.insertMention}
            roomId={chat.selectedRoom?.room.id ?? null}
            onVoiceTranscription={(text) => {
              const transcript = text.trim()
              if (!transcript) return
              chat.setInputValue('')
              chat.setMentionQuery(null)
              chat.setMentionResults([])
              chat.setDispatchSummary(null)
              voice.audioPlayerRef.current?.stop()
              setLastVoiceTranscript(isVoiceBattlePrep ? transcript : null)
              scheduleGuidanceRefresh({
                extraTurn: {
                  speaker: 'user',
                  text: transcript,
                  metadata: {
                    ...(liveCoachGuidanceMetadata || {}),
                    source: isLiveCoachSession ? 'live_coach_voice_transcription' : 'voice_transcription',
                    trainingMode: 'voice',
                    interactionMode: 'turn_based',
                  },
                },
                autoOpenOnSignal: true,
                minIntervalMs: GUIDANCE_AUTO_MIN_INTERVAL_MS,
              })
              setTimeout(chat.scrollToBottom, 100)
            }}
            onVoiceRecorderStateChange={handleVoiceRecorderStateChange}
            onVideoClick={() => setVideoRecorderOpen(true)}
            videoActive={videoRecorderOpen}
            onLiveCoachClick={isLiveCoachSession ? handleRequestGuidance : coaching.handleStartLiveCoaching}
            coachingSending={isLiveCoachSession ? guidanceLoading : coaching.coachingSending}
            sendError={chat.sendError}
          />
        </div>

        {showEmotionSidebar && (
          <EmotionSidebar
            messages={chat.selectedRoom?.messages ?? []}
            personaMap={personaMap}
            onClose={() => setShowEmotionSidebar(false)}
            onExpand={() => setShowEmotionCurve(true)}
          />
        )}
      </div>
      </div>

      {/* Right column: context panel */}
      <ContextPanel
        personas={roomPersonas}
        collapsed={!showContextPanel}
        onToggle={() => setShowContextPanel((v) => !v)}
        onExpandEmotion={() => setShowEmotionCurve(true)}
      />

      {/* Overlay panels */}
      <CoachingPanel
        open={coaching.coachingOpen}
        mode={coaching.coachingMode}
        messages={coaching.coachingMessages}
        streamingContent={coaching.coachingStreaming}
        sending={coaching.coachingSending}
        inputValue={coaching.coachingInput}
        onInputChange={coaching.setCoachingInput}
        onSend={coaching.handleSendCoaching}
        onClose={() => coaching.setCoachingOpen(false)}
        sessionId={coaching.coachingSessionId}
        listRef={coaching.coachingListRef}
      />

      <EmotionCurve
        open={showEmotionCurve}
        onClose={() => setShowEmotionCurve(false)}
        messages={chat.selectedRoom?.messages ?? []}
        personaMap={personaMap}
      />

      {analysis.analysisResult && (
        <AnalysisPanel
          result={analysis.analysisResult}
          reportList={analysis.analysisReportList}
          analyzingRoom={analysis.analyzingRoom}
          onClose={() => analysis.setAnalysisResult(null)}
          onSelectReport={analysis.handleSelectReport}
          onGenerateNewReport={analysis.handleGenerateNewReport}
          onScrollToMessage={analysis.handleScrollToMessage}
        />
      )}

      <CheatSheetComponent
        open={cheatSheetData !== null}
        onClose={() => setCheatSheetData(null)}
        data={cheatSheetData}
        personaName={cheatSheetPersona}
      />

      {/* Mobile bottom sheet */}
      {mobileSheet && (
        <div className="chat-mobile-sheet">
          <div className="chat-mobile-sheet-header">
            <h4>
              {mobileSheet === 'cheatsheet' && tr('锦囊', 'Tips')}
              {mobileSheet === 'coaching' && tr('教练', 'Coach')}
              {mobileSheet === 'analysis' && tr('评分', 'Score')}
              {mobileSheet === 'emotion' && tr('情绪', 'Emotion')}
            </h4>
            <button
              className="chat-mobile-sheet-close"
              onClick={() => setMobileSheet(null)}
            >
              <X size={16} />
            </button>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
            {mobileSheet === 'cheatsheet' && tr('点击上方"结束备战"按钮后，可在此查看话术锦囊。', 'Tap “End Battle Prep” above to view your cheat sheet here.')}
            {mobileSheet === 'coaching' && tr('点击开始获取AI教练的实时指导建议。', 'Tap start to get real-time AI coaching suggestions.')}
            {mobileSheet === 'analysis' && tr('完成对话后，可在此查看对话评分。', 'After finishing the conversation, view scores here.')}
            {mobileSheet === 'emotion' && tr('对话进行中会在此展示情绪变化曲线。', 'Emotion trends will appear here during the conversation.')}
          </p>
        </div>
      )}
    </>
  )
}

/* ------------------------------------------------------------------ */
/*  ChatPage — top-level page component                                */
/* ------------------------------------------------------------------ */

export default function ChatPage() {
  const { roomId: roomIdParam } = useParams<{ roomId: string }>()
  const navigate = useNavigate()
  const { tr } = useI18n()

  const roomId = roomIdParam ? Number(roomIdParam) : null

  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  return (
    <div className={`chat-page${roomId ? ' has-room' : ''}`}>
      {/* Left column: room list */}
      <div className="chat-page-left">
        <RoomList
          selectedRoomId={roomId}
          onSelectRoom={(room: ChatRoom) => {
            navigate(APP_ROUTES.conversation(room.id))
          }}
          onCreateRoom={() => setShowCreateDialog(true)}
          onRoomDeleted={(id) => {
            if (roomId === id) {
              navigate(APP_ROUTES.conversations)
            }
          }}
          refreshKey={refreshKey}
        />
      </div>

      {/* Center + Right columns */}
      {roomId ? (
        <ChatProvider roomId={roomId}>
          <ChatAreaWithLoad
            roomId={roomId}
            onRefresh={() => setRefreshKey((k) => k + 1)}
          />
        </ChatProvider>
      ) : (
        <div className="chat-page-empty">
          <div className="chat-page-empty-icon">
            <MessageCircle size={32} strokeWidth={1.5} />
          </div>
          <h2>{tr('选择一个对话房间', 'Choose a conversation room')}</h2>
          <p>{tr('从左侧打开已有房间，或新建一个普通对话。', 'Open an existing room, or create a regular conversation.')}</p>
          <button
            className="chat-page-empty-cta"
            onClick={() => setShowCreateDialog(true)}
          >
            <Plus size={16} />
            {tr('新建对话房间', 'New conversation room')}
          </button>
        </div>
      )}

      <CreateRoomDialog
        open={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onCreated={(newRoomId: number) => {
          setRefreshKey((k) => k + 1)
          navigate(APP_ROUTES.conversation(newRoomId))
        }}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Wrapper that loads room detail on mount / roomId change            */
/* ------------------------------------------------------------------ */

function ChatAreaWithLoad({
  roomId,
}: {
  roomId: number
  onRefresh: () => void
}) {
  const { chat } = useChatContext()
  const { tr } = useI18n()

  useEffect(() => {
    chat.loadRoomDetail(roomId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId])

  // Re-trigger room list refresh after sending a message
  // (The parent refreshKey is bumped via onRefresh, but we also
  // want to refresh when new messages arrive. For now, rely on the
  // RoomList's own fetchRooms triggered by refreshKey.)

  if (!chat.selectedRoom) {
    return (
      <div className="chat-page-empty">
        <div className="chat-page-empty-icon">
          <MessageCircle size={32} strokeWidth={1.5} />
        </div>
        <h2>{tr('加载中...', 'Loading...')}</h2>
        <p>{tr('正在加载对话内容', 'Loading conversation content')}</p>
      </div>
    )
  }

  return <ChatArea />
}
