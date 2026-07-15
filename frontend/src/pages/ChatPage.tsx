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
  ArrowLeft,
  PhoneCall,
  Volume2,
  VolumeX,
  Video,
  X,
  Lightbulb,
  Radio,
} from 'lucide-react'
import { useAppContext } from '../contexts/AppContext'
import { ChatProvider, useChatContext } from '../contexts/ChatContext'
import RoomList from '../components/RoomList'
import CreateRoomDialog from '../components/CreateRoomDialog'
import MessageList from '../components/chat/MessageList'
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
  getTrainingGuidanceStreamUrl,
  getTrainingSessionReport,
  requestTrainingGuidance,
  type GuideEventDTO,
  type TrainingSessionReportDTO,
  type TrainingGuidanceResponse,
  type TranscriptTurnDTO,
} from '../services/trainingSession'
import { uploadVideoAnswer } from '../services/trainingStudio'
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
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n } from '../i18n'
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

function compactStrings(values: Array<string | null | undefined | false>): string[] {
  return values.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
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

const scenarioDifficultyLabels: Record<ScenarioTrainingDifficulty, string> = {
  easy: '简单',
  medium: '进阶',
  hard: '困难',
  expert: '专家',
}

const scenarioCategoryLabels: Record<ScenarioTrainingCategory, string> = {
  sales: '销售',
  customer_service: '服务',
  negotiation: '谈判',
  interview: '面试',
}

const trainingModeLabels: Record<string, string> = {
  text: '文字',
  voice: '语音',
  video: '视频',
}

const interactionModeLabels: Record<string, string> = {
  turn_based: '轮次对练',
  realtime: '实时对练',
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
  const { tr } = useI18n()
  const preparedVoiceRoomRef = React.useRef<number | null>(null)
  const guidanceTurnsRef = React.useRef<TranscriptTurnDTO[]>([])
  const guidanceTimerRef = React.useRef<number | null>(null)
  const guidanceInFlightRef = React.useRef(false)
  const guidanceRequestSeqRef = React.useRef(0)
  const guidanceLastRequestedAtRef = React.useRef(0)
  const lastAutoGuidanceMessageKeyRef = React.useRef<string | null>(null)
  const guidanceEventSourceRef = React.useRef<EventSource | null>(null)
  const guidanceStreamVersionRef = React.useRef(0)
  const trainingMode = getTrainingModeFromLocation(location.search, location.state)
  const interactionMode = getInteractionModeFromLocation(location.search, location.state)
  const trainingSessionId = getTrainingSessionIdFromLocation(location.search, location.state)
  const trainingProfile = getTrainingProfileFromLocation(location.search, location.state)
  const liveCoachLanguagePair = getLiveCoachLanguagePairFromLocation(location.search, location.state)
  const isLiveCoachSession = trainingProfile === 'live_coach'
  const progressScope = React.useMemo(() => ({
    userId: currentUser?.userId ?? null,
    teamId: currentUser?.teamId ?? null,
  }), [currentUser?.teamId, currentUser?.userId])
  const scenarioTrainingId = getScenarioTrainingIdFromLocation(location.search, location.state)
    ?? getScenarioTrainingIdFromProgress(trainingSessionId, progressScope)
  const scenarioTrainingCard = getScenarioTrainingCardById(scenarioTrainingId)

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
  const [cheatSheetData, setCheatSheetData] = useState<CheatSheetData | null>(null)
  const [cheatSheetPersona, setCheatSheetPersona] = useState('')
  const selectedRoomId = chat.selectedRoom?.room.id ?? null
  const selectedRoomType = chat.selectedRoom?.room.type
  const sendChatMessage = chat.handleSend

  useEffect(() => {
    setTrainingSessionCompleted(false)
    setGuidanceOpen(false)
    setGuidanceError(null)
    setGuidanceEvents([])
    setGuidanceStreamConnected(false)
    guidanceRequestSeqRef.current += 1
    lastAutoGuidanceMessageKeyRef.current = null
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
        setGuidanceError(tr('Live guidance stream failed', 'Live guidance stream failed'))
      }
    })

    es.addEventListener('guidance_error', (event) => {
      if (!isCurrentStream()) return
      try {
        const data = JSON.parse(event.data)
        setGuidanceError(String(data.detail || tr('Live guidance stream failed', 'Live guidance stream failed')))
      } catch {
        setGuidanceError(tr('Live guidance stream failed', 'Live guidance stream failed'))
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
          room_id: message.room_id,
          sender_id: message.sender_id,
          sender_type: message.sender_type,
          emotion_score: message.emotion_score,
          emotion_label: message.emotion_label,
        },
      }))
  }, [selectedRoomMessages])

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
      setGuidanceError(e instanceof Error ? e.message : tr('Live guidance failed', 'Live guidance failed'))
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
    const success = await sendChatMessage()
    if (!success) return
    if (trainingSessionId && outgoingText) {
      scheduleGuidanceRefresh({
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
    scheduleGuidanceRefresh,
    selectedRoomType,
    sendChatMessage,
    trainingSessionId,
  ])

  const handleKeyDown = (e: React.KeyboardEvent) => {
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

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    chat.handleInputChange(
      e,
      personaMap,
      chat.selectedRoom?.room.type,
      chat.selectedRoom?.room.persona_ids,
    )
  }

  const isTrainingSession = Boolean(trainingSessionId)
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
  const scenarioOpeningLineFromState = getStateStringValue(location.state, 'scenarioOpeningLine')
  const trainingBackPath = scenarioTrainingId ? '/scenario-training' : '/training-studio'
  const trainingContextTitle = scenarioTrainingCard?.title
    || scenarioTitleFromState
    || chat.selectedRoom?.room.name
    || tr('训练会话', 'Training session')
  const trainingContextSubtitle = scenarioTrainingCard
    ? compactStrings([
      scenarioTrainingCard.persona.role,
      scenarioTrainingCard.learnerRole ? `${tr('你扮演', 'You play')}: ${scenarioTrainingCard.learnerRole}` : null,
    ]).join(' · ')
    : compactStrings([
      counterpartName,
      trainingMode ? trainingModeLabels[trainingMode] : null,
      interactionModeLabels[interactionMode],
    ]).join(' · ')
  const trainingContextTags = compactStrings([
    scenarioTrainingCard ? scenarioCategoryLabels[scenarioTrainingCard.category] : null,
    scenarioTrainingCard ? scenarioDifficultyLabels[scenarioTrainingCard.difficulty] : null,
    scenarioTrainingCard?.required ? tr('必练', 'Required') : scenarioTrainingCard ? tr('选练', 'Optional') : null,
    trainingMode ? trainingModeLabels[trainingMode] : null,
    interactionModeLabels[interactionMode],
  ])
  const trainingContextDescription = scenarioTrainingCard?.description
    || scenarioOpeningLineFromState
    || tr('本轮训练已连接 AI 陪练，完成对话后可结束练习并生成复盘。', 'This training session is connected to an AI coach. End the practice when you are ready for review.')
  const trainingContextOpeningLine = scenarioTrainingCard?.openingLine || scenarioOpeningLineFromState
  const trainingContextPoints = scenarioTrainingCard?.trainingPoints.slice(0, 3).join(' / ')
  const trainingInputPlaceholder = scenarioTrainingCard?.category === 'sales' || scenarioTrainingCard?.category === 'customer_service'
    ? tr('输入你想对客户说的话，Enter 发送', 'Type what you want to say to the customer. Enter to send')
    : tr('输入你的回应，Enter 发送', 'Type your response. Enter to send')

  const liveCoachLanguageSummary = compactStrings([
    liveCoachLanguagePair.sourceLanguage,
    liveCoachLanguagePair.targetLanguage,
  ]).join(' -> ')
  const resolvedTrainingBackPath = isLiveCoachSession ? '/live-coach' : trainingBackPath
  const resolvedTrainingContextTitle = isLiveCoachSession ? tr('Live coach', 'Live coach') : trainingContextTitle
  const resolvedTrainingContextSubtitle = isLiveCoachSession
    ? compactStrings([
      tr('Real conversation', 'Real conversation'),
      liveCoachLanguageSummary || null,
      interactionModeLabels[interactionMode],
    ]).join(' / ')
    : trainingContextSubtitle
  const resolvedTrainingContextTags = isLiveCoachSession
    ? compactStrings([
      tr('Live coach', 'Live coach'),
      liveCoachLanguagePair.sourceLanguage,
      liveCoachLanguagePair.targetLanguage,
      interactionModeLabels[interactionMode],
    ])
    : trainingContextTags
  const resolvedTrainingContextDescription = isLiveCoachSession
    ? tr('Private AI coaching is connected to the live transcript and review loop.', 'Private AI coaching is connected to the live transcript and review loop.')
    : trainingContextDescription
  const resolvedTrainingContextOpeningLine = isLiveCoachSession ? null : trainingContextOpeningLine
  const resolvedTrainingContextPoints = isLiveCoachSession ? null : trainingContextPoints
  const resolvedTrainingInputPlaceholder = isLiveCoachSession
    ? tr('Type a meeting line or your next reply. Enter to send', 'Type a meeting line or your next reply. Enter to send')
    : trainingInputPlaceholder
  const guidanceBarTitle = isLiveCoachSession ? tr('Live coach', 'Live coach') : tr('Realtime guidance', 'Realtime guidance')
  const guidanceReadyText = isLiveCoachSession
    ? tr('Ready to coach this conversation', 'Ready to coach this conversation')
    : tr('Ready during this training session', 'Ready during this training session')
  const guidanceStreamingText = isLiveCoachSession
    ? tr('Watching the live transcript', 'Watching the live transcript')
    : tr('Streaming during this training session', 'Streaming during this training session')
  const guidanceActionText = isLiveCoachSession ? tr('Ask coach', 'Ask coach') : tr('Guide me', 'Guide me')
  const realtimeBarTitle = isLiveCoachSession
    ? tr('Live conversation coach', 'Live conversation coach')
    : tr('实时语音训练', 'Realtime voice practice')
  const realtimeBarCopy = isLiveCoachSession
    ? liveCoachLanguageSummary || tr('Realtime channel is bound to live coaching', 'Realtime channel is bound to live coaching')
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
          source: isLiveCoachSession ? 'live_coach_realtime_voice' : 'realtime_voice',
          trainingMode: 'voice',
          interactionMode: 'realtime',
          trainingProfile,
          realtimeRole: role,
          ...(isLiveCoachSession
            ? {
                sourceLanguage: liveCoachLanguagePair.sourceLanguage,
                targetLanguage: liveCoachLanguagePair.targetLanguage,
                translationStrategy: 'text_first_mvp',
              }
            : {}),
        },
      },
      autoOpenOnSignal: true,
      minIntervalMs: GUIDANCE_AUTO_MIN_INTERVAL_MS,
    })
    setTimeout(chat.scrollToBottom, 100)
  }, [
    chat.scrollToBottom,
    isLiveCoachSession,
    liveCoachLanguagePair.sourceLanguage,
    liveCoachLanguagePair.targetLanguage,
    scheduleGuidanceRefresh,
    trainingProfile,
  ])

  const handleCompleteTrainingSession = React.useCallback(async () => {
    if (!trainingSessionId || trainingSessionCompleting) return
    setTrainingSessionCompleting(true)
    try {
      const session = await completeTrainingSession(trainingSessionId, { generate_report: true })
      setTrainingSessionCompleted(true)
      const reportId = Number(session.report_id)
      const scenarioScore = Number.isFinite(reportId) && reportId > 0
        ? await getTrainingSessionReport(trainingSessionId)
          .then(extractTrainingReportScore)
          .catch(() => undefined)
        : undefined
      if (scenarioTrainingId) {
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
      } else {
        await analysis.handleAnalyze()
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : tr('璁粌瀹屾垚澶辫触', 'Failed to complete training session'))
    } finally {
      setTrainingSessionCompleting(false)
    }
  }, [analysis, progressScope, scenarioTrainingId, trainingSessionCompleting, trainingSessionId, tr])

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

  const handleVideoRecorded = React.useCallback(async (result: VideoAnswerResult) => {
    setVideoRecorderOpen(false)
    if (isVideoBattlePrep) {
      setVideoAnswerStatus('uploading')
      setVideoAnswerError(null)
    }
    const fallbackCaption = isVideoBattlePrep
      ? tr('我提交了一段视频回答，请继续追问或总结。', 'I submitted a recorded video answer. Please continue with a follow-up or summary.')
      : undefined
    let videoUrl = result.url
    let videoSize = result.size
    try {
      const uploaded = await uploadVideoAnswer(result.blob)
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
          text: chat.inputValue.trim() || fallbackCaption || tr('I submitted a recorded video answer.', 'I submitted a recorded video answer.'),
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
      <div className="chat-page-center">
      {/* Chat header */}
      <div className="chat-page-header">
        <div className="chat-page-header-left">
          <button
            className="chat-page-back-btn"
            onClick={() => navigate('/chat')}
            title={tr('返回对话列表', 'Back to conversation list')}
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
                  <span key={tag}>{tag}</span>
                ))}
              </div>
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

          <div className="chat-page-training-scene">
            {scenarioTrainingCard?.customerProfile && (
              <p>
                <strong>{tr('客户画像', 'Customer profile')}:</strong>
                <span>{scenarioTrainingCard.customerProfile}</span>
              </p>
            )}
            <p>
              <strong>{tr('场景描述', 'Scenario')}:</strong>
              <span>{resolvedTrainingContextDescription}</span>
            </p>
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
                : guidanceEvents[0]?.message || (
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
            {guidanceLoading ? tr('Thinking', 'Thinking') : guidanceActionText}
          </button>
        </section>
      )}

      {trainingSessionId && guidanceOpen && (
        <section className="chat-page-guidance-panel" data-testid="training-guidance-panel">
          <div className="guidance-panel-header">
            <strong>{tr('Live coach', 'Live coach')}</strong>
            <button
              type="button"
              onClick={() => setGuidanceOpen(false)}
              title={tr('Close guidance', 'Close guidance')}
              aria-label={tr('Close guidance', 'Close guidance')}
            >
              <X size={14} />
            </button>
          </div>
          {guidanceLoading && guidanceEvents.length === 0 && (
            <div className="guidance-empty">{tr('Reading the latest turn', 'Reading the latest turn')}</div>
          )}
          {!guidanceLoading && guidanceEvents.length === 0 && !guidanceError && (
            <div className="guidance-empty">{tr('No guidance yet', 'No guidance yet')}</div>
          )}
          {guidanceError && (
            <div className="guidance-error">{guidanceError}</div>
          )}
          {guidanceEvents.length > 0 && (
            <div className="guidance-event-list">
              {guidanceEvents.map((event, index) => (
                <article
                  className={`guidance-card ${event.severity || 'info'}`}
                  key={`${event.event_type}-${index}`}
                >
                  <div className="guidance-card-header">
                    <span>{event.title}</span>
                    <small>{event.event_type.replace(/_/g, ' ')}</small>
                  </div>
                  <p>{event.message}</p>
                  {event.suggested_text && <blockquote>{event.suggested_text}</blockquote>}
                </article>
              ))}
            </div>
          )}
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
                  style={{ background: primaryPersona?.avatar_color || '#2D9C6F' }}
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
                  style={{ background: primaryPersona?.avatar_color || '#2D9C6F' }}
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
            voiceEnabled={voice.voiceEnabled}
            voiceMuted={voice.voiceMuted}
            onToggleVoice={voice.toggleVoice}
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
                    source: 'voice_transcription',
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
            navigate(`/chat/${room.id}`)
          }}
          onCreateRoom={() => setShowCreateDialog(true)}
          onRoomDeleted={(id) => {
            if (roomId === id) {
              navigate('/chat')
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
          <h2>{tr('选择一个对话开始练习', 'Choose a conversation to start practicing')}</h2>
          <p>{tr('从左侧选择聊天室，或创建一个新的对话', 'Select a chat room from the left, or create a new conversation')}</p>
          <button
            className="chat-page-empty-cta"
            onClick={() => setShowCreateDialog(true)}
          >
            <Plus size={16} />
            {tr('新建聊天室', 'New Chat Room')}
          </button>
        </div>
      )}

      <CreateRoomDialog
        open={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onCreated={(newRoomId: number) => {
          setRefreshKey((k) => k + 1)
          navigate(`/chat/${newRoomId}`)
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
