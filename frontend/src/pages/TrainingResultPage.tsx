import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  Clock3,
  ExternalLink,
  GitBranch,
  Loader2,
  MessageCircle,
  RotateCcw,
  Trophy,
} from 'lucide-react'
import { fetchRoomDetail, type ChatRoomDetail, type Message } from '../services/api'
import {
  getTrainingConversationBranchInfo,
  getReviewAssistantMaterialReviewDisplayState,
  getTrainingSession,
  getTrainingSessionReport,
  listTrainingMaterialToolConsumerMaterials,
  requestReviewAssistantMaterialReview,
  type MaterialReviewDTO,
  type TrainingMaterialAssetSummaryDTO,
  type TrainingConversationBranchInfo,
  type TrainingSessionDTO,
  type TrainingSessionReportDTO,
} from '../services/trainingSession'
import { buildTrainingModeChatPath } from '../services/trainingMode'
import { useAuthContext } from '../contexts/AuthContext'
import { getLiveCoachLanguageLabel } from '../data/liveCoachLanguages'
import { useI18n, type Locale, type Translate, type TranslateInline, type TranslationKey } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { PageHeader, PageShell } from '../components/ui/page'
import { StateBlock, StateSpinner } from '../components/ui/state'
import {
  getScenarioTrainingCardById,
  getScenarioTrainingProgress,
  type ScenarioTrainingProgress,
} from '../data/trainingScenarios'
import './TrainingResultPage.css'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

interface ResultDimension {
  key: string
  title: string
  score?: number
  label?: string
  rationale?: string
  suggestions: string[]
  status?: string
}

interface InsightCard {
  key: string
  title: string
  body: string
  meta?: string
}

interface CoachReplayEvent {
  key: string
  eventType: string
  severity: string
  title: string
  message: string
  suggestedText?: string
  createdAt?: string | null
}

type LocalizedText = readonly [zh: string, en: string]

const TRAINING_GUIDANCE_MESSAGE_SOURCE = 'training_live_guidance'

const reportDimensionLabels: Record<string, LocalizedText> = {
  content_delivery: ['内容表达', 'Content delivery'],
  camera_presence: ['镜头表现', 'Camera presence'],
}

const modeLabelKeys: Record<string, TranslationKey> = {
  text: 'training.mode.text.label',
  voice: 'training.mode.voice.label',
  video: 'training.mode.video.label',
  realtime: 'training.mode.realtime.label',
  live_coach: 'training.mode.liveCoach.label',
}

function translateLabel(label: LocalizedText, tr: TranslateInline): string {
  return tr(label[0], label[1])
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const record = asRecord(item)
        return record ? [record] : []
      })
    : []
}

function coerceScore(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined
  return Math.max(0, Math.min(100, Math.round(value)))
}

function formatDateTime(value: string | null | undefined, locale: Locale, tr: TranslateInline): string {
  if (!value) return tr('未记录', 'Not recorded')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined,
  tr: TranslateInline,
): string {
  if (!startedAt || !completedAt) return tr('未记录', 'Not recorded')
  const start = new Date(startedAt).getTime()
  const end = new Date(completedAt).getTime()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return tr('未记录', 'Not recorded')
  const seconds = Math.round((end - start) / 1000)
  if (seconds < 60) return tr('{seconds} 秒', '{seconds}s', { seconds })
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return tr('{minutes} 分 {seconds} 秒', '{minutes}m {seconds}s', {
    minutes,
    seconds: String(remainder).padStart(2, '0'),
  })
}

function gradeLabel(score: number | undefined, tr: TranslateInline): string {
  if (score === undefined) return tr('待生成', 'Pending')
  if (score >= 90) return tr('优秀', 'Excellent')
  if (score >= 80) return tr('强', 'Strong')
  if (score >= 70) return tr('稳定', 'Solid')
  return tr('需要练习', 'Needs work')
}

function statusLabel(status: string | undefined, tr: TranslateInline): string {
  if (status === 'completed') return tr('已完成', 'Completed')
  if (status === 'active') return tr('进行中', 'In progress')
  if (status === 'created') return tr('未开始', 'Not started')
  if (status === 'failed') return tr('失败', 'Failed')
  return tr('未知', 'Unknown')
}

function getScenarioTitle(session: TrainingSessionDTO | null, tr: TranslateInline): string {
  if (!session) return tr('训练会话', 'Training session')
  const scenario = getScenarioTrainingCardById(session.scenario_template_id)
  if (scenario) return scenario.title
  const metadata = asRecord(session.task_config.metadata)
  const scenarioTraining = asRecord(metadata?.scenario_training)
  const metadataTitle = asString(scenarioTraining?.title)
  return metadataTitle || session.task_config.tech_stack[0] || session.task_config.role || tr('训练会话', 'Training session')
}

function getScenarioDescription(session: TrainingSessionDTO | null): string {
  if (!session) return ''
  const scenario = getScenarioTrainingCardById(session.scenario_template_id)
  return scenario?.description || session.task_config.tech_stack[1] || session.task_config.category
}

function isLiveCoachTrainingSession(session: TrainingSessionDTO | null): boolean {
  const metadata = asRecord(session?.task_config.metadata)
  return metadata?.trainingProfile === 'live_coach'
    || metadata?.source === 'live_coach_mvp'
    || asRecord(metadata?.liveCoach) !== null
}

function getLiveCoachLanguages(session: TrainingSessionDTO | null): {
  sourceLanguage: string | null
  targetLanguage: string | null
} {
  const metadata = asRecord(session?.task_config.metadata)
  const liveCoach = asRecord(metadata?.liveCoach)
  return {
    sourceLanguage: asString(liveCoach?.sourceLanguage) || asString(metadata?.sourceLanguage) || null,
    targetLanguage: asString(liveCoach?.targetLanguage) || asString(metadata?.targetLanguage) || null,
  }
}

function getTrainingReplyLanguage(session: TrainingSessionDTO | null): string | null {
  const sessionMetadata = asRecord(session?.metadata)
  const metadata = asRecord(session?.task_config.metadata)
  const scenarioTraining = asRecord(metadata?.scenario_training)
  const language = asRecord(metadata?.language)
  const candidates = [
    metadata?.replyLanguage,
    metadata?.reply_language,
    scenarioTraining?.replyLanguage,
    scenarioTraining?.reply_language,
    language?.replyLanguage,
    language?.reply_language,
    sessionMetadata?.replyLanguage,
    sessionMetadata?.reply_language,
  ]
  for (const candidate of candidates) {
    const text = asString(candidate)
    if (text) return text
  }
  return null
}

function getLiveCoachLanguagePair(
  session: TrainingSessionDTO | null,
  locale: Locale,
  tr: TranslateInline,
): string {
  const { sourceLanguage, targetLanguage } = getLiveCoachLanguages(session)
  if (!sourceLanguage && !targetLanguage) {
    return tr('双语辅助已预留', 'Bilingual assist ready')
  }
  const sourceLabel = getLiveCoachLanguageLabel(sourceLanguage, locale) || tr('来源语言', 'source language')
  const targetLabel = getLiveCoachLanguageLabel(targetLanguage, locale) || tr('目标语言', 'target language')
  return tr('{source} 到 {target}', '{source} to {target}', {
    source: sourceLabel,
    target: targetLabel,
  })
}

function modeLabel(mode: string | undefined, t: Translate, tr: TranslateInline): string {
  if (!mode) return tr('未知', 'unknown')
  const labelKey = modeLabelKeys[mode]
  return labelKey ? t(labelKey) : mode
}

function getDimension(
  content: Record<string, unknown>,
  key: string,
  tr: TranslateInline,
): ResultDimension | null {
  const record = asRecord(content[key])
  if (!record) return null
  const status = asString(record.status)
  if (status === 'not_applicable') return null
  const score = coerceScore(record.score)
  const rationale = asString(record.rationale)
  const label = asString(record.label)
  return {
    key,
    title: reportDimensionLabels[key] ? translateLabel(reportDimensionLabels[key], tr) : key.replace(/_/g, ' '),
    score,
    label,
    rationale,
    suggestions: stringArray(record.suggestions),
    status,
  }
}

function collectDimensions(
  content: Record<string, unknown>,
  progressScore?: number,
  tr?: TranslateInline,
): ResultDimension[] {
  const dimensions = Object.keys(reportDimensionLabels)
    .flatMap((key) => {
      if (!tr) return []
      const dimension = getDimension(content, key, tr)
      return dimension ? [dimension] : []
    })

  if (dimensions.length === 0 && progressScore !== undefined) {
    return [{
      key: 'overall_progress',
      title: tr ? tr('整体进度', 'Overall progress') : 'Overall progress',
      score: progressScore,
      label: tr ? gradeLabel(progressScore, tr) : undefined,
      rationale: tr ? tr('分数已从场景训练进度同步。', 'Score synced from scenario training progress.') : undefined,
      suggestions: [],
      status: 'observed',
    }]
  }

  return dimensions
}

function collectSuggestions(content: Record<string, unknown>, dimensions: ResultDimension[]): string[] {
  const suggestions = new Set<string>()
  dimensions.forEach((dimension) => {
    dimension.suggestions.forEach((suggestion) => suggestions.add(suggestion))
  })
  recordArray(content.communication_suggestions).forEach((item) => {
    const suggestion = asString(item.suggestion)
    if (suggestion) suggestions.add(suggestion)
  })
  recordArray(content.micro_drills).forEach((item) => {
    const prompt = asString(item.prompt)
    if (prompt) suggestions.add(prompt)
  })
  recordArray(content.rewrite_demos).forEach((item) => {
    const rewritten = asString(item.rewritten)
    if (rewritten) suggestions.add(rewritten)
  })
  return [...suggestions].slice(0, 6)
}

function collectInsights(content: Record<string, unknown>, tr: TranslateInline): InsightCard[] {
  const effectiveArguments = recordArray(content.effective_arguments).slice(0, 3).map((item, index) => ({
    key: `argument-${index}`,
    title: asString(item.argument) || tr('有效表达', 'Effective argument'),
    body: asString(item.effectiveness) || tr('这是一段值得保留的有效沟通动作。', 'Captured as an effective move in this conversation.'),
    meta: asString(item.target_persona),
  }))

  const evidence = recordArray(content.evidence_reviews).slice(0, 2).map((item, index) => ({
    key: `evidence-${index}`,
    title: asString(item.claim) || tr('证据片段', 'Evidence moment'),
    body: asString(item.insight) || asString(item.evidence) || tr('这是一段来自转写的高信号片段。', 'A high-signal moment from the transcript.'),
    meta: tr('证据', 'Evidence'),
  }))

  const highSignal = recordArray(content.high_signal_moments).slice(0, 2).map((item, index) => ({
    key: `moment-${index}`,
    title: asString(item.title) || tr('高信号片段', 'High-signal moment'),
    body: asString(item.recommendation) || asString(item.why_it_matters) || tr('下一次练习前值得回看。', 'Worth revisiting before the next drill.'),
    meta: asString(item.moment_type),
  }))

  return [...effectiveArguments, ...evidence, ...highSignal].slice(0, 5)
}

function messageContent(message: Message, tr: TranslateInline): string {
  const marker = '[video-answer]'
  const index = message.content.indexOf(marker)
  if (index < 0) return message.content
  return message.content.slice(0, index).trim() || tr('视频回答已提交。', 'Video answer submitted.')
}

function messageSpeaker(message: Message, isLiveCoachSession: boolean, tr: TranslateInline): string {
  if (message.sender_type === 'user') return tr('你', 'You')
  if (message.sender_type === 'system') return tr('系统', 'System')
  return isLiveCoachSession ? tr('AI 教练', 'AI coach') : tr('对手', 'Counterpart')
}

function messageMetadata(message: Message): Record<string, unknown> | null {
  return asRecord(message.metadata)
}

function isTrainingGuidanceMessage(message: Message): boolean {
  return messageMetadata(message)?.source === TRAINING_GUIDANCE_MESSAGE_SOURCE
}

function coachEventFromMessage(message: Message): CoachReplayEvent | null {
  const metadata = messageMetadata(message)
  if (!metadata || metadata.source !== TRAINING_GUIDANCE_MESSAGE_SOURCE) return null
  const guidance = asRecord(metadata.guidance) ?? {}
  const eventType = asString(guidance.event_type) || asString(metadata.eventType) || 'guidance'
  const severity = asString(guidance.severity) || asString(metadata.severity) || 'info'
  const title = asString(guidance.title) || message.content.split('\n')[0]?.trim() || eventType
  const body = asString(guidance.message) || message.content
  const suggestedText = asString(guidance.suggested_text)
  const createdAt = asString(guidance.created_at) || asString(metadata.persistedAt) || message.timestamp
  return {
    key: String(message.id),
    eventType,
    severity,
    title,
    message: body,
    suggestedText: suggestedText || undefined,
    createdAt,
  }
}

function compactBranchText(value: string, maxLength = 72): string {
  const text = value.replace(/\s+/g, ' ').trim()
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 3)}...`
}

function branchPathNodeText(
  item: TrainingConversationBranchInfo['selectedPath'][number],
  index: number,
): string {
  return `${index + 1}. ${compactBranchText(item.content || item.publicId)}`
}

function branchSourceLabel(source: TrainingConversationBranchInfo['source'], tr: TranslateInline): string {
  if (source === 'session') return tr('来自会话', 'from session')
  if (source === 'report') return tr('来自报告', 'from report')
  return tr('来自本地进度', 'from local progress')
}

function branchSourceDetailText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  const source = branchSourceLabel(info.source, tr)
  return info.sourceDetail ? `${source} · ${info.sourceDetail}` : source
}

function branchPathTextStateLabel(
  state: TrainingConversationBranchInfo['pathTextState'],
  tr: TranslateInline,
): string {
  if (state === 'with_text') return tr('包含路径正文', 'Path text included')
  if (state === 'id_only') return tr('只有节点 ID', 'Node IDs only')
  return tr('只有引用', 'References only')
}

function branchConversationRefText(info: TrainingConversationBranchInfo): string {
  return [info.provider, info.conversationId].filter(Boolean).join(' · ')
}

function branchPathStatusText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  const count = info.pathCount || info.selectedPath.length
  if (count > 0) return tr('当前路径 {count} 个节点', 'Current path, {count} nodes', { count })
  if (info.selectedTailMessageId) return tr('已记录尾节点引用', 'Tail node reference recorded')
  return tr('已记录分支引用', 'Branch reference recorded')
}

function branchPathNoticeText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  if (info.pathTextState === 'reference_only') {
    return tr('metadata 只保存了分支或尾节点引用，暂时没有可预览的路径正文。', 'Only branch or tail references were saved in metadata; no path text is available to preview.')
  }
  if (info.pathTextState === 'id_only') {
    return tr('metadata 只保存了路径节点 ID，没有保存消息正文。', 'Only path node IDs were saved in metadata; message text was not included.')
  }
  return ''
}

function branchPathDetailText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  if (info.pathSummary) return compactBranchText(info.pathSummary, 96)
  return branchPathNoticeText(info, tr)
}

function branchLastReplyEmptyText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  if (info.pathTextState === 'id_only') {
    return tr('metadata 中只有消息 ID，无法显示最后回复正文。', 'Only message IDs are present in metadata, so the last reply text cannot be shown.')
  }
  return tr('metadata 中没有最后回复正文。', 'No last reply text was saved in metadata.')
}

function coachEventTypeLabel(eventType: string, tr: TranslateInline): string {
  if (eventType === 'risk') return tr('风险提醒', 'Risk alert')
  if (eventType === 'next_reply') return tr('下一句建议', 'Next reply')
  if (eventType === 'delivery_nudge') return tr('表达提醒', 'Delivery nudge')
  if (eventType === 'ask_back') return tr('追问建议', 'Ask-back prompt')
  if (eventType === 'omission') return tr('遗漏提醒', 'Missing piece')
  return eventType.replace(/_/g, ' ')
}

function coachSeverityLabel(severity: string, tr: TranslateInline): string {
  if (severity === 'warning') return tr('需要注意', 'Needs attention')
  if (severity === 'error' || severity === 'critical') return tr('高风险', 'High risk')
  if (severity === 'success') return tr('已捕捉', 'Captured')
  return tr('提示', 'Info')
}

function materialMetadata(material: TrainingMaterialAssetSummaryDTO): Record<string, unknown> {
  return asRecord(material.metadata_excerpt) ?? {}
}

function materialTitle(material: TrainingMaterialAssetSummaryDTO): string {
  const metadata = materialMetadata(material)
  return asString(metadata.title) || asString(metadata.name) || material.name
}

function materialSummary(material: TrainingMaterialAssetSummaryDTO): string {
  const metadata = materialMetadata(material)
  return asString(metadata.summary)
    || asString(metadata.description)
    || asString(metadata.usageScope)
    || material.key
}

function materialContentExcerpt(material: TrainingMaterialAssetSummaryDTO): string {
  return asString(material.content_excerpt)
}

function materialTags(material: TrainingMaterialAssetSummaryDTO): string[] {
  const metadata = materialMetadata(material)
  const tags = [
    ...stringArray(metadata.tags),
    ...stringArray(metadata.labels),
    asString(metadata.materialType) || asString(metadata.material_type),
    asString(metadata.scenarioId) || asString(metadata.scenario_id),
  ].filter(Boolean)
  return Array.from(new Set(tags)).slice(0, 4)
}

function materialReferenceMeta(
  material: TrainingMaterialAssetSummaryDTO,
  tr: TranslateInline,
): string {
  const metadata = materialMetadata(material)
  return [
    asString(metadata.sourceType) || asString(metadata.source),
    asString(metadata.language),
    material.content_type || '',
  ].filter(Boolean).join(' · ') || tr('安全摘要', 'Safe excerpt')
}

function materialReviewSourceMeta(review: MaterialReviewDTO | null, tr: TranslateInline): string {
  if (!review) return tr('待生成', 'Pending')
  const sources = [
    review.source_state.report_used ? tr('报告', 'Report') : '',
    review.source_state.replay_used ? tr('回放', 'Replay') : '',
    review.source_state.material_snippet_used ? tr('素材片段', 'Material snippet') : '',
  ].filter(Boolean)
  return sources.join(' · ') || tr('deterministic fallback', 'deterministic fallback')
}

function materialReviewLimitMeta(review: MaterialReviewDTO | null, tr: TranslateInline): string {
  if (!review) return ''
  const limits = [
    review.limits.material_selection_truncated ? tr('素材已截断', 'materials truncated') : '',
    review.limits.material_snippets_truncated ? tr('片段已截断', 'snippets truncated') : '',
    review.limits.report_context_truncated ? tr('报告上下文已截断', 'report context truncated') : '',
    review.limits.replay_transcript_truncated ? tr('回放已截断', 'replay truncated') : '',
  ].filter(Boolean)
  return limits.join(' · ')
}

function materialReviewPointKey(
  point: MaterialReviewDTO['matched_points'][number],
  index: number,
): string {
  return `${point.material_id}-${index}-${point.point.slice(0, 24)}`
}

export default function TrainingResultPage() {
  const navigate = useNavigate()
  const { locale, t, tr } = useI18n()
  const { sessionId: routeSessionId } = useParams<{ sessionId: string }>()
  const [searchParams] = useSearchParams()
  const { currentUser } = useAuthContext()
  const progressScope = useMemo(() => ({
    userId: currentUser?.userId ?? null,
    teamId: currentUser?.teamId ?? null,
  }), [currentUser?.teamId, currentUser?.userId])
  const sessionId = routeSessionId?.trim()
    || searchParams.get('session_id')?.trim()
    || searchParams.get('trainingSessionId')?.trim()
    || ''
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [session, setSession] = useState<TrainingSessionDTO | null>(null)
  const [report, setReport] = useState<TrainingSessionReportDTO | null>(null)
  const [reportError, setReportError] = useState<string | null>(null)
  const [roomDetail, setRoomDetail] = useState<ChatRoomDetail | null>(null)
  const [roomError, setRoomError] = useState<string | null>(null)
  const [materialsState, setMaterialsState] = useState<LoadState>('idle')
  const [materials, setMaterials] = useState<TrainingMaterialAssetSummaryDTO[]>([])
  const [materialsTotal, setMaterialsTotal] = useState(0)
  const [materialsError, setMaterialsError] = useState<string | null>(null)
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null)
  const [materialReviewState, setMaterialReviewState] = useState<LoadState>('idle')
  const [materialReview, setMaterialReview] = useState<MaterialReviewDTO | null>(null)
  const [materialReviewError, setMaterialReviewError] = useState<string | null>(null)
  const [progress, setProgress] = useState<ScenarioTrainingProgress>(() => (
    getScenarioTrainingProgress(progressScope)
  ))

  useEffect(() => {
    setProgress(getScenarioTrainingProgress(progressScope))
  }, [progressScope])

  useEffect(() => {
    if (!sessionId) {
      setLoadState('error')
      setError(tr('缺少训练会话 ID。', 'Missing training session id.'))
      return
    }

    let cancelled = false
    setLoadState('loading')
    setError(null)
    setReport(null)
    setReportError(null)
    setRoomDetail(null)
    setRoomError(null)

    getTrainingSession(sessionId)
      .then(async (nextSession) => {
        if (cancelled) return
        setSession(nextSession)

        const roomId = Number(nextSession.room_id)
        const reportPromise = nextSession.report_id || nextSession.status === 'completed'
          ? getTrainingSessionReport(nextSession.session_id)
          : Promise.resolve(null)
        const roomPromise = Number.isFinite(roomId) && roomId > 0
          ? fetchRoomDetail(roomId)
          : Promise.resolve(null)

        const [reportResult, roomResult] = await Promise.allSettled([reportPromise, roomPromise])
        if (cancelled) return

        if (reportResult.status === 'fulfilled') {
          setReport(reportResult.value)
        } else {
          setReportError(getErrorMessage(reportResult.reason, tr('复盘报告暂未生成。', 'Report is not ready yet.')))
        }

        if (roomResult.status === 'fulfilled') {
          setRoomDetail(roomResult.value)
        } else {
          setRoomError(getErrorMessage(roomResult.reason, tr('无法加载回放消息。', 'Could not load replay messages.')))
        }

        setLoadState('ready')
      })
      .catch((requestError: unknown) => {
        if (cancelled) return
        setError(getErrorMessage(requestError, tr('无法加载训练结果。', 'Could not load training result.')))
        setLoadState('error')
      })

    return () => {
      cancelled = true
    }
  }, [sessionId, tr])

  useEffect(() => {
    let cancelled = false
    setMaterialsState('loading')
    setMaterialsError(null)

    listTrainingMaterialToolConsumerMaterials({ limit: 5, includeContentExcerpt: true })
      .then((result) => {
        if (cancelled) return
        setMaterials(result.items)
        setMaterialsTotal(result.total)
        setMaterialsState('ready')
      })
      .catch((requestError: unknown) => {
        if (cancelled) return
        setMaterials([])
        setMaterialsTotal(0)
        setMaterialsError(getErrorMessage(requestError, tr('无法加载训练素材。', 'Could not load training materials.')))
        setMaterialsState('error')
      })

    return () => {
      cancelled = true
    }
  }, [currentUser?.teamId, currentUser?.userId, tr])

  useEffect(() => {
    setSelectedMaterialId((current) => {
      if (current !== null && materials.some((material) => material.id === current)) {
        return current
      }
      return materials[0]?.id ?? null
    })
  }, [materials])

  const selectedMaterialReady = selectedMaterialId !== null
    && materials.some((material) => material.id === selectedMaterialId)

  useEffect(() => {
    if (!sessionId || !selectedMaterialReady || selectedMaterialId === null) {
      setMaterialReview(null)
      setMaterialReviewError(null)
      setMaterialReviewState('idle')
      return
    }

    let cancelled = false
    setMaterialReview(null)
    setMaterialReviewError(null)
    setMaterialReviewState('loading')

    requestReviewAssistantMaterialReview({
      sessionId,
      selectedMaterialIds: [selectedMaterialId],
    })
      .then((result) => {
        if (cancelled) return
        setMaterialReview(result)
        setMaterialReviewState('ready')
      })
      .catch((requestError: unknown) => {
        if (cancelled) return
        setMaterialReview(null)
        setMaterialReviewError(getErrorMessage(requestError, tr('无法生成素材对照。', 'Could not build material review.')))
        setMaterialReviewState('error')
      })

    return () => {
      cancelled = true
    }
  }, [selectedMaterialId, selectedMaterialReady, sessionId, tr])

  const scenarioId = session?.scenario_template_id || ''
  const scenarioProgress = scenarioId ? progress[scenarioId] : undefined
  const content = useMemo(() => asRecord(report?.content) ?? {}, [report])
  const branchInfo = useMemo(
    () => getTrainingConversationBranchInfo({ session, report, progress: scenarioProgress }),
    [report, scenarioProgress, session],
  )
  const branchPathPreview = branchInfo?.selectedPath.slice(-5) ?? []
  const branchPathPreviewOffset = branchInfo
    ? Math.max(0, branchInfo.selectedPath.length - branchPathPreview.length)
    : 0
  const branchPathNotice = branchInfo ? branchPathNoticeText(branchInfo, tr) : ''
  const branchPathDetail = branchInfo ? branchPathDetailText(branchInfo, tr) : ''
  const branchConversationRef = branchInfo ? branchConversationRefText(branchInfo) : ''
  const progressScore = coerceScore(scenarioProgress?.score)
  const dimensions = useMemo(
    () => collectDimensions(content, progressScore, tr),
    [content, progressScore, tr],
  )
  const dimensionScores = dimensions
    .map((dimension) => dimension.score)
    .filter((score): score is number => score !== undefined)
  const dimensionAverage = dimensionScores.length
    ? Math.round(dimensionScores.reduce((sum, score) => sum + score, 0) / dimensionScores.length)
    : undefined
  const overallScore = dimensionAverage ?? progressScore
  const scoreSourceLabel = dimensionAverage !== undefined
    ? tr('来自报告', 'from report')
    : progressScore !== undefined
      ? tr('来自进度', 'from progress')
      : tr('暂无分数来源', 'No score source')
  const dimensionMetaText = dimensions.length > 0
    ? tr('{count} 项 · {source}', '{count} items · {source}', {
      count: dimensions.length,
      source: scoreSourceLabel,
    })
    : scoreSourceLabel
  const failureReason = session?.status === 'failed'
    ? session.failure_reason || scenarioProgress?.failureReason || tr('训练会话失败，但后端未返回失败原因。', 'The training session failed, but no backend failure reason was returned.')
    : ''
  const suggestions = useMemo(() => collectSuggestions(content, dimensions), [content, dimensions])
  const insights = useMemo(() => collectInsights(content, tr), [content, tr])
  const selectedMaterial = useMemo(
    () => materials.find((material) => material.id === selectedMaterialId) ?? materials[0] ?? null,
    [materials, selectedMaterialId],
  )
  const selectedMaterialTags = selectedMaterial ? materialTags(selectedMaterial) : []
  const selectedMaterialContentExcerpt = selectedMaterial ? materialContentExcerpt(selectedMaterial) : ''
  const materialReviewDisplayState = getReviewAssistantMaterialReviewDisplayState({
    materialsState,
    materialsCount: materials.length,
    materialReviewState,
    materialReview,
    materialReviewError,
  })
  const materialReviewLimit = materialReviewLimitMeta(materialReview, tr)
  const isLiveCoachSession = isLiveCoachTrainingSession(session)
  const liveCoachLanguages = getLiveCoachLanguages(session)
  const liveCoachLanguagePair = getLiveCoachLanguagePair(session, locale, tr)
  const sourceBadges = [
    session ? tr('会话', 'Session') : '',
    report ? (isLiveCoachSession ? tr('教练报告', 'Coach report') : tr('复盘报告', 'Report')) : '',
    roomDetail ? (isLiveCoachSession ? tr('真实转写', 'Transcript') : tr('聊天转写', 'Transcript')) : '',
    scenarioProgress ? tr('本地进度', 'Local progress') : '',
  ].filter((label): label is string => Boolean(label))
  const scenarioTitle = getScenarioTitle(session, tr)
  const scenarioDescription = getScenarioDescription(session)
  const roomId = Number(session?.room_id)
  const chatPath = session && Number.isFinite(roomId) && roomId > 0
    ? buildTrainingModeChatPath(
        roomId,
        session.mode,
        session.session_id,
        isLiveCoachSession ? 'realtime' : undefined,
        {
          trainingProfile: isLiveCoachSession ? 'live_coach' : null,
          replyLanguage: getTrainingReplyLanguage(session),
          sourceLanguage: liveCoachLanguages.sourceLanguage,
          targetLanguage: liveCoachLanguages.targetLanguage,
        },
      )
    : null
  const messages = useMemo(() => roomDetail?.messages ?? [], [roomDetail?.messages])
  const coachEvents = useMemo(
    () => messages.flatMap((message) => {
      const event = coachEventFromMessage(message)
      return event ? [event] : []
    }),
    [messages],
  )
  const replayMessages = useMemo(
    () => messages.filter((message) => !isTrainingGuidanceMessage(message)),
    [messages],
  )
  const turnCount = Math.ceil(Math.max(session?.message_count ?? 0, replayMessages.length) / 2)

  if (loadState === 'loading' || loadState === 'idle') {
    return (
      <PageShell width="wide" className="training-result-page">
        <StateBlock
          className="training-result-state"
          description={tr('正在读取会话、复盘报告和回放转写。', 'Reading the session, report, and replay transcript.')}
          icon={<StateSpinner />}
          size="lg"
          title={tr('正在加载训练结果...', 'Loading training result...')}
          tone="loading"
        />
      </PageShell>
    )
  }

  if (loadState === 'error') {
    return (
      <PageShell width="wide" className="training-result-page">
        <StateBlock
          actions={(
            <Button asChild variant="primary">
              <Link to={APP_ROUTES.reviewSessions}>
                {tr('返回训练记录', 'Back to training records')}
              </Link>
            </Button>
          )}
          className="training-result-state error"
          description={error}
          icon={<AlertCircle size={22} />}
          size="lg"
          title={tr('训练结果不可用', 'Training result unavailable')}
          tone="danger"
        />
      </PageShell>
    )
  }

  return (
    <PageShell width="wide" className="training-result-page">
      <PageHeader
        className="training-result-header"
        leading={(
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)} aria-label={tr('返回', 'Go back')}>
            <ArrowLeft size={17} />
          </Button>
        )}
        eyebrow={isLiveCoachSession ? tr('实时陪跑复盘', 'Live coach review') : tr('训练结果', 'Training result')}
        title={scenarioTitle}
        description={(scenarioDescription || isLiveCoachSession) ? (
          <>
            {scenarioDescription}
            {isLiveCoachSession && (
              <>
                {scenarioDescription ? <br /> : null}
                {tr('双语辅助：{pair}', 'Bilingual assist: {pair}', { pair: liveCoachLanguagePair })}
              </>
            )}
          </>
        ) : undefined}
        meta={sourceBadges.length > 0 ? (
          <div className="training-result-source-strip" aria-label={tr('复盘数据来源', 'Review data sources')}>
            {sourceBadges.map((label) => (
              <Badge key={label} tone="neutral">{label}</Badge>
            ))}
          </div>
        ) : undefined}
        actions={(
          <>
            <Button asChild variant="secondary" size="sm" className="training-result-secondary-link">
              <Link to={APP_ROUTES.practiceScenarios}>
                <RotateCcw size={15} />
                {tr('回到训练', 'Back to training')}
              </Link>
            </Button>
            <Button asChild variant="secondary" size="sm" className="training-result-secondary-link">
              <Link to={APP_ROUTES.reviewSessions}>
                {tr('训练记录', 'Training records')}
              </Link>
            </Button>
            {chatPath && (
              <Button asChild variant="primary" size="sm" className="training-result-primary-link">
                <Link to={chatPath}>
                  <ExternalLink size={15} />
                  {isLiveCoachSession ? tr('打开陪跑房间', 'Open coach room') : tr('打开对话', 'Open chat')}
                </Link>
              </Button>
            )}
          </>
        )}
      />

      <section className="training-result-main-grid">
        <article className={`training-result-score-card ${session?.status ?? 'unknown'}`}>
          <div className="training-result-score-icon">
            {session?.status === 'failed'
              ? <AlertCircle size={22} />
              : session?.status === 'completed'
                ? <Trophy size={22} />
                : <Clock3 size={22} />}
          </div>
          <div className="training-result-score-value">
            {overallScore === undefined ? '--' : overallScore}
          </div>
          <div className="training-result-grade">
            {session?.status === 'failed' ? statusLabel(session.status, tr) : gradeLabel(overallScore, tr)}
          </div>
          <div className="training-result-score-source">
            {scoreSourceLabel}
          </div>
          {failureReason && (
            <div className="training-result-empty-inline">
              {failureReason}
            </div>
          )}
          <div className="training-result-score-meta">
            <span>
              <strong>{tr('状态', 'Status')}</strong>
              {statusLabel(session?.status, tr)}
            </span>
            <span>
              <strong>{tr('时长', 'Duration')}</strong>
              {formatDuration(session?.started_at, session?.completed_at, tr)}
            </span>
            <span>
              <strong>{tr('轮次', 'Turns')}</strong>
              {turnCount}
            </span>
            <span>
              <strong>{tr('模式', 'Mode')}</strong>
              {isLiveCoachSession ? t('training.mode.liveCoach.label') : modeLabel(session?.mode, t, tr)}
            </span>
          </div>
        </article>

        <article className="training-result-card training-result-dimensions">
          <div className="training-result-card-head">
            <h2>{tr('维度评分', 'Dimension scores')}</h2>
            <span>{dimensionMetaText}</span>
          </div>
          {dimensions.length > 0 ? (
            <div className="training-result-dimension-list">
              {dimensions.map((dimension) => (
                <div className="training-result-dimension-row" key={dimension.key}>
                  <div className="training-result-dimension-copy">
                    <strong>{dimension.title}</strong>
                    <span>{dimension.rationale || dimension.label || dimension.status || tr('已在报告中记录', 'Observed in report')}</span>
                  </div>
                  <div className="training-result-dimension-meter" aria-label={`${dimension.title} ${tr('分数', 'score')}`}>
                    <span style={{ width: `${dimension.score ?? 0}%` }} />
                  </div>
                  <em>{dimension.score ?? '--'}</em>
                </div>
              ))}
            </div>
          ) : (
            <div className="training-result-empty-inline">
              {reportError || tr('暂未生成维度评分。', 'No dimension score has been generated yet.')}
            </div>
          )}
        </article>
      </section>

      {branchInfo && (
        <section
          className="training-result-card training-result-branch"
          aria-label={tr('训练路径/分支', 'Training path / branch')}
        >
          <div className="training-result-card-head training-result-branch-head">
            <h2>
              <GitBranch size={15} />
              {tr('路径上下文', 'Path context')}
            </h2>
            <span>{branchSourceDetailText(branchInfo, tr)}</span>
          </div>
          <div className="training-result-branch-grid">
            <div className="training-result-branch-item wide">
              <span>{tr('当前路径', 'Current path')}</span>
              <strong>{branchPathStatusText(branchInfo, tr)}</strong>
              {branchPathDetail && (
                <em
                  className={branchInfo.pathSummary ? undefined : 'empty'}
                  title={branchInfo.pathSummary || branchPathDetail}
                >
                  {branchPathDetail}
                </em>
              )}
            </div>
            <div className="training-result-branch-item">
              <span>{tr('正文状态', 'Text state')}</span>
              <strong>{branchPathTextStateLabel(branchInfo.pathTextState, tr)}</strong>
            </div>
            {branchInfo.branchId && (
              <div className="training-result-branch-item">
                <span>{tr('当前分支', 'Current branch')}</span>
                <strong title={branchInfo.branchId}>{compactBranchText(branchInfo.branchId, 48)}</strong>
              </div>
            )}
            {branchInfo.forkPointMessageId && (
              <div className="training-result-branch-item">
                <span>{tr('分叉点', 'Fork point')}</span>
                <strong title={branchInfo.forkPointMessageId}>
                  {compactBranchText(branchInfo.forkPointMessageId, 48)}
                </strong>
              </div>
            )}
            {branchInfo.selectedTailMessageId && (
              <div className="training-result-branch-item">
                <span>{tr('尾节点', 'Tail node')}</span>
                <strong title={branchInfo.selectedTailMessageId}>
                  {compactBranchText(branchInfo.selectedTailMessageId, 48)}
                </strong>
              </div>
            )}
            <div className="training-result-branch-item wide">
              <span>{tr('最后回复', 'Last reply')}</span>
              {branchInfo.lastReplyPreview ? (
                <strong title={branchInfo.lastReplyPreview}>{compactBranchText(branchInfo.lastReplyPreview, 96)}</strong>
              ) : (
                <em className="empty">{branchLastReplyEmptyText(branchInfo, tr)}</em>
              )}
            </div>
            {branchConversationRef && (
              <div className="training-result-branch-item">
                <span>{tr('会话引用', 'Conversation ref')}</span>
                <strong title={branchConversationRef}>{compactBranchText(branchConversationRef, 48)}</strong>
              </div>
            )}
          </div>
          {branchPathNotice && branchPathDetail !== branchPathNotice && (
            <p className="training-result-branch-note">{branchPathNotice}</p>
          )}
          {branchPathPreview.length > 0 && (
            <div className="training-result-branch-path" aria-label={tr('已选择路径摘要', 'Selected path summary')}>
              {branchPathPreview.map((item, index) => (
                <span
                  key={`${item.publicId}-${index}`}
                  className={item.content.trim() ? undefined : 'id-only'}
                  title={item.content || item.publicId}
                >
                  {branchPathNodeText(item, branchPathPreviewOffset + index)}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

      {reportError && dimensions.length > 0 && (
        <section className="training-result-notice">
          <Clock3 size={16} />
          <span>{reportError}</span>
        </section>
      )}

      <section className="training-result-dual-grid">
        <article className="training-result-card">
          <div className="training-result-card-head">
            <h2>{isLiveCoachSession ? tr('教练摘要', 'Coach summary') : tr('AI 摘要', 'AI summary')}</h2>
            {report?.created_at && <span>{formatDateTime(report.created_at, locale, tr)}</span>}
          </div>
          <p className="training-result-summary">
            {report?.summary || (isLiveCoachSession
              ? tr('实时转写已保存；结束会话并生成报告后，这里会显示风险、下一步和行动项摘要。', 'The live transcript is saved. After you end the session and generate a report, this area will show risks, next steps, and action items.')
              : tr('本次训练已记录，但 AI 复盘报告暂未生成。', 'This session is recorded, but the AI report is not available yet.'))}
          </p>
        </article>

        <article className="training-result-card">
          <div className="training-result-card-head">
            <h2>{isLiveCoachSession ? tr('下一步行动', 'Next actions') : tr('改进重点', 'Improvement focus')}</h2>
            <span>{tr('{count} 条建议', '{count} tips', { count: suggestions.length })}</span>
          </div>
          {suggestions.length > 0 ? (
            <ol className="training-result-suggestions">
              {suggestions.map((suggestion) => (
                <li key={suggestion}>{suggestion}</li>
              ))}
            </ol>
          ) : (
            <div className="training-result-empty-inline">
              {isLiveCoachSession
                ? tr('生成报告后，这里会沉淀承诺事项、遗漏问题和下一句优化方向。', 'After the report is generated, commitments, missing questions, and next-reply improvements will appear here.')
                : tr('报告生成后会显示改进建议。', 'Suggestions will appear after the report is generated.')}
            </div>
          )}
        </article>
      </section>

      <section className="training-result-card training-result-review-assistant">
        <div className="training-result-card-head training-result-review-assistant-head">
          <h2>
            <BookOpen size={15} />
            {tr('复盘助手', 'Review assistant')}
          </h2>
          <span>
            {materialsState === 'loading'
              ? tr('读取素材', 'Loading materials')
              : tr('{count} 条素材', '{count} materials', { count: materialsTotal })}
          </span>
        </div>
        {materialsState === 'loading' ? (
          <div className="training-result-review-assistant-state">
            <Loader2 className="training-result-spin" size={16} />
            <span>{tr('正在读取可引用素材。', 'Loading reference materials.')}</span>
          </div>
        ) : materialsError ? (
          <div className="training-result-notice compact">
            <AlertCircle size={15} />
            <span>{materialsError}</span>
          </div>
        ) : materials.length === 0 ? (
          <div className="training-result-empty-inline">
            {tr('当前账号暂无可引用训练素材。', 'No scoped training materials are available.')}
          </div>
        ) : (
          <div className="training-result-review-assistant-grid">
            <div className="training-result-material-list" aria-label={tr('训练素材', 'Training materials')}>
              {materials.map((material) => {
                const selected = selectedMaterial?.id === material.id
                const tags = materialTags(material)
                return (
                  <Button
                    key={material.id}
                    variant="ghost"
                    className={`training-result-material-option${selected ? ' selected' : ''}`}
                    onClick={() => setSelectedMaterialId(material.id)}
                    aria-pressed={selected}
                  >
                    <strong>{materialTitle(material)}</strong>
                    <span>{materialSummary(material)}</span>
                    {tags.length > 0 && (
                      <em>
                        {tags.map((tag) => (
                          <i key={tag}>{tag}</i>
                        ))}
                      </em>
                    )}
                  </Button>
                )
              })}
            </div>
            {selectedMaterial && (
              <div className="training-result-review-reference">
                <span>{materialReferenceMeta(selectedMaterial, tr)}</span>
                <strong>{materialTitle(selectedMaterial)}</strong>
                <p>{materialSummary(selectedMaterial)}</p>
                {selectedMaterialContentExcerpt ? (
                  <div className="training-result-review-reference-content">
                    <span>{tr('素材正文片段', 'Material snippet')}</span>
                    <p>{selectedMaterialContentExcerpt}</p>
                    {selectedMaterial.content_excerpt_truncated && (
                      <em>{tr('已截断', 'Truncated')}</em>
                    )}
                  </div>
                ) : (
                  <div className="training-result-review-reference-content empty">
                    {tr('暂无可展示正文片段。', 'No material snippet is available.')}
                  </div>
                )}
                {selectedMaterialTags.length > 0 && (
                  <div className="training-result-review-reference-tags">
                    {selectedMaterialTags.map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                )}
                <div className="training-result-material-review-panel" aria-live="polite">
                  <div className="training-result-material-review-head">
                    <span>{tr('素材对照', 'Material review')}</span>
                    <em>{materialReviewSourceMeta(materialReview, tr)}</em>
                  </div>
                  {materialReviewDisplayState === 'loading' ? (
                    <div className="training-result-material-review-state">
                      <Loader2 className="training-result-spin" size={15} />
                      <span>{tr('正在生成素材对照。', 'Building material review.')}</span>
                    </div>
                  ) : materialReviewDisplayState === 'error' ? (
                    <div className="training-result-notice compact">
                      <AlertCircle size={15} />
                      <span>{materialReviewError}</span>
                    </div>
                  ) : materialReviewDisplayState === 'empty' ? (
                    <div className="training-result-material-review-state empty">
                      {tr('素材对照暂未返回命中、遗漏或改写建议。', 'No matched points, missed points, or rewrite suggestions returned yet.')}
                    </div>
                  ) : materialReview && (
                    <>
                      <div className="training-result-material-review-stats">
                        <span>{tr('命中 {count}', 'Matched {count}', { count: materialReview.matched_points.length })}</span>
                        <span>{tr('遗漏 {count}', 'Missed {count}', { count: materialReview.missed_points.length })}</span>
                        <span>{tr('改写 {count}', 'Rewrites {count}', { count: materialReview.suggested_rewrites.length })}</span>
                      </div>
                      {materialReviewLimit && (
                        <p className="training-result-material-review-limit">{materialReviewLimit}</p>
                      )}
                      <div className="training-result-material-review-sections">
                        <div>
                          <strong>{tr('命中要点', 'Matched points')}</strong>
                          {materialReview.matched_points.length > 0 ? (
                            <ul>
                              {materialReview.matched_points.map((point, index) => (
                                <li key={materialReviewPointKey(point, index)}>
                                  <span>{point.point}</span>
                                  {point.evidence && <em>{point.evidence}</em>}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p>{tr('暂无明确命中。', 'No clear matches yet.')}</p>
                          )}
                        </div>
                        <div>
                          <strong>{tr('遗漏要点', 'Missed points')}</strong>
                          {materialReview.missed_points.length > 0 ? (
                            <ul>
                              {materialReview.missed_points.map((point, index) => (
                                <li key={materialReviewPointKey(point, index)}>
                                  <span>{point.point}</span>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p>{tr('本轮没有明显遗漏。', 'No obvious misses in this pass.')}</p>
                          )}
                        </div>
                        <div className="wide">
                          <strong>{tr('下一次可练', 'Next drill')}</strong>
                          {materialReview.suggested_rewrites.length > 0 ? (
                            <ol>
                              {materialReview.suggested_rewrites.map((suggestion) => (
                                <li key={suggestion}>{suggestion}</li>
                              ))}
                            </ol>
                          ) : (
                            <p>{tr('暂无改写建议。', 'No rewrite suggestions yet.')}</p>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {insights.length > 0 && (
        <section className="training-result-card training-result-insights">
          <div className="training-result-card-head">
            <h2>{tr('值得回看的片段', 'Replay-worthy moments')}</h2>
            <span>{tr('来自报告', 'from report')}</span>
          </div>
          <div className="training-result-insight-grid">
            {insights.map((insight) => (
              <article key={insight.key}>
                {insight.meta && <span>{insight.meta}</span>}
                <strong>{insight.title}</strong>
                <p>{insight.body}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {isLiveCoachSession && (
        <section className="training-result-card training-result-coach-events">
          <div className="training-result-card-head">
            <h2>{tr('教练事件时间线', 'Coach event timeline')}</h2>
            <span>{tr('{count} 条事件', '{count} events', { count: coachEvents.length })}</span>
          </div>
          {coachEvents.length > 0 ? (
            <div className="training-result-coach-event-list">
              {coachEvents.map((event) => (
                <article className={`training-result-coach-event ${event.severity}`} key={event.key}>
                  <div className="training-result-coach-event-head">
                    <span>{coachEventTypeLabel(event.eventType, tr)}</span>
                    <em>{coachSeverityLabel(event.severity, tr)}</em>
                  </div>
                  <strong>{event.title}</strong>
                  <p>{event.message}</p>
                  {event.suggestedText && (
                    <blockquote>
                      <span>{tr('下一句建议', 'Suggested next line')}</span>
                      {event.suggestedText}
                    </blockquote>
                  )}
                  {event.createdAt && <time>{formatDateTime(event.createdAt, locale, tr)}</time>}
                </article>
              ))}
            </div>
          ) : (
            <div className="training-result-empty-inline">
              {tr('本次会话还没有保存的实时教练事件。', 'No saved live coach events yet.')}
            </div>
          )}
        </section>
      )}

      <section className="training-result-card training-result-replay">
        <div className="training-result-card-head">
          <h2>{isLiveCoachSession ? tr('真实对话回放', 'Real conversation replay') : tr('对话回放', 'Conversation replay')}</h2>
          <span>{tr('{count} 条消息', '{count} messages', { count: replayMessages.length })}</span>
        </div>
        {roomError && (
          <div className="training-result-notice compact">
            <AlertCircle size={15} />
            <span>{roomError}</span>
          </div>
        )}
        {replayMessages.length === 0 ? (
          <div className="training-result-empty-replay">
            <MessageCircle size={24} />
            <p>{tr('本次会话还没有可回放的消息。', 'No replay messages loaded for this session.')}</p>
          </div>
        ) : (
          <div className="training-result-message-list">
            {replayMessages.map((message) => (
              <article
                key={message.id}
                className={`training-result-message ${message.sender_type}`}
              >
                <div className="training-result-message-avatar">
                  {messageSpeaker(message, isLiveCoachSession, tr).slice(0, 1)}
                </div>
                <div>
                  <span>
                    {messageSpeaker(message, isLiveCoachSession, tr)}
                    {message.timestamp ? ` · ${formatDateTime(message.timestamp, locale, tr)}` : ''}
                  </span>
                  <p>{messageContent(message, tr)}</p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

    </PageShell>
  )
}
