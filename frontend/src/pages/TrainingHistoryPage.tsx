import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  GitBranch,
  History,
  Loader2,
  RotateCcw,
  Search,
  Trophy,
} from 'lucide-react'
import { fetchScenarioTrainingProgress } from '../services/scenarioTraining'
import {
  getTrainingConversationBranchInfo,
  listTrainingSessions,
  type TrainingConversationBranchInfo,
  type TrainingSessionDTO,
  type TrainingSessionStatus,
} from '../services/trainingSession'
import { buildTrainingModeChatPath } from '../services/trainingMode'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n, type Locale, type Translate, type TranslateInline, type TranslationKey } from '../i18n'
import { PageHeader, PageShell } from '../components/ui/page'
import { APP_ROUTES } from '../appRoutes'
import {
  getScenarioTrainingCardById,
  getScenarioTrainingProgress,
  mergeScenarioTrainingProgressRecords,
  saveScenarioTrainingProgress,
  type ScenarioTrainingCategory,
  type ScenarioTrainingDifficulty,
  type ScenarioTrainingStatus,
  type ScenarioTrainingProgress,
  type ScenarioTrainingProgressItem,
} from '../data/trainingScenarios'
import {
  getScenarioCategoryLabel,
  getScenarioDifficultyLabel,
  getScenarioStatusFilterLabel,
  getScenarioStatusLabel,
  scenarioCategoryOptions,
  scenarioDifficultyOptions,
  scenarioStatusOptions,
  type ScenarioStatusFilter,
} from '../utils/scenarioLabels'
import './TrainingHistoryPage.css'

type HistoryStatus = ScenarioTrainingStatus
type StatusFilter = ScenarioStatusFilter
type LocalizedText = readonly [zh: string, en: string]

interface HistoryEntry {
  key: string
  sessionId?: string
  scenarioId?: string
  title: string
  description: string
  difficulty?: string
  category?: string
  status: HistoryStatus
  score?: number
  scoreStatus?: 'ready' | 'pending'
  reportId?: string
  roomId?: string | null
  mode?: TrainingSessionDTO['mode']
  messageCount?: number
  startedAt?: string | null
  completedAt?: string | null
  lastPracticedAt?: string
  branchInfo?: TrainingConversationBranchInfo
  source: 'session' | 'progress'
}

const statusOptions: StatusFilter[] = ['all', ...scenarioStatusOptions]

const modeLabelKeys: Record<string, TranslationKey> = {
  text: 'training.mode.text.label',
  voice: 'training.mode.voice.label',
  video: 'training.mode.video.label',
  realtime: 'training.mode.realtime.label',
  live_coach: 'training.mode.liveCoach.label',
}

const sourceLabels: Record<HistoryEntry['source'], LocalizedText> = {
  session: ['训练会话', 'Session'],
  progress: ['本地进度', 'Local progress'],
}

function translateLabel(label: LocalizedText, tr: TranslateInline): string {
  return tr(label[0], label[1])
}

function searchLabel(zhText: string, enText: string): string {
  return `${zhText} ${enText}`
}

function translatedDifficulty(value: string | undefined, tr: TranslateInline): string {
  if (!value) return ''
  return scenarioDifficultyOptions.includes(value as ScenarioTrainingDifficulty)
    ? getScenarioDifficultyLabel(value as ScenarioTrainingDifficulty, tr)
    : value
}

function translatedCategory(value: string | undefined, tr: TranslateInline): string {
  if (!value) return ''
  return scenarioCategoryOptions.includes(value as ScenarioTrainingCategory)
    ? getScenarioCategoryLabel(value as ScenarioTrainingCategory, tr)
    : value
}

function translatedMode(value: string | undefined, t: Translate): string {
  if (!value) return ''
  const labelKey = modeLabelKeys[value]
  return labelKey ? t(labelKey) : value
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

function normalizeSessionStatus(status: TrainingSessionStatus): HistoryStatus {
  if (status === 'completed') return 'completed'
  if (status === 'failed') return 'failed'
  if (status === 'created') return 'not_started'
  return 'in_progress'
}

function coerceScore(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined
  return Math.max(0, Math.min(100, Math.round(value)))
}

function formatDate(value: string | null | undefined, locale: Locale, tr: TranslateInline): string {
  if (!value) return tr('未记录', 'Not recorded')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

function formatClock(value: string | null | undefined, locale: Locale): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function compactHistoryBranchText(value: string, maxLength = 30): string {
  const text = value.replace(/\s+/g, ' ').trim()
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 3)}...`
}

function historyBranchPathTextStateText(
  state: TrainingConversationBranchInfo['pathTextState'],
  tr: TranslateInline,
): string {
  if (state === 'with_text') return tr('路径正文已保存', 'path text saved')
  if (state === 'id_only') return tr('只有节点 ID', 'node IDs only')
  return tr('只有路径引用', 'path refs only')
}

function historyBranchPathText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  const count = info.pathCount || info.selectedPath.length
  if (count > 0) return tr('当前路径：{count} 节点', 'Current path: {count} nodes', { count })
  if (info.selectedTailMessageId) return tr('当前路径：尾节点引用', 'Current path: tail ref')
  return tr('当前路径：分支引用', 'Current path: branch ref')
}

function historyBranchEmptyText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  if (info.pathTextState === 'id_only') {
    return tr('仅保存了消息 ID。', 'Only message IDs were saved.')
  }
  return tr('未保存路径预览。', 'No path preview saved.')
}

function historyBranchTitle(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  return [
    historyBranchPathText(info, tr),
    historyBranchPathTextStateText(info.pathTextState, tr),
    info.branchId ? tr('分支：{value}', 'Branch: {value}', { value: info.branchId }) : '',
    info.forkPointMessageId ? tr('分叉点：{value}', 'Fork point: {value}', { value: info.forkPointMessageId }) : '',
    info.selectedTailMessageId ? tr('尾节点：{value}', 'Tail: {value}', { value: info.selectedTailMessageId }) : '',
    info.pathSummary ? compactHistoryBranchText(info.pathSummary, 90) : '',
  ].filter(Boolean).join(' · ')
}

function historyBranchTagText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  if (info.pathCount) return tr('{count} 节点', '{count} nodes', { count: info.pathCount })
  if (info.branchId) return compactHistoryBranchText(info.branchId)
  return tr('路径引用', 'Path ref')
}

function historyBranchSummaryText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  if (info.lastReplyPreview) {
    return tr('最后回复：{value}', 'Last reply: {value}', {
      value: compactHistoryBranchText(info.lastReplyPreview, 72),
    })
  }
  if (info.pathSummary) return compactHistoryBranchText(info.pathSummary, 72)
  if (info.forkPointMessageId) {
    return tr('分叉点：{value}', 'Fork point: {value}', {
      value: compactHistoryBranchText(info.forkPointMessageId, 48),
    })
  }
  if (info.selectedTailMessageId) {
    return tr('尾节点：{value}', 'Tail: {value}', {
      value: compactHistoryBranchText(info.selectedTailMessageId, 48),
    })
  }
  return historyBranchEmptyText(info, tr)
}

function historyEntryMetaText(entry: HistoryEntry, tr: TranslateInline): string {
  const details: string[] = []
  if (typeof entry.messageCount === 'number') {
    details.push(tr('{count} 条消息', '{count} messages', { count: entry.messageCount }))
  }
  if (entry.sessionId) {
    details.push(tr('会话 {value}', 'Session {value}', {
      value: compactHistoryBranchText(entry.sessionId, 18),
    }))
  } else if (entry.scenarioId) {
    details.push(tr('场景 {value}', 'Scenario {value}', {
      value: compactHistoryBranchText(entry.scenarioId, 18),
    }))
  }
  return details.join(' · ') || tr('暂无记录详情', 'No record details')
}

function historyTimeContext(entry: HistoryEntry, locale: Locale, tr: TranslateInline): string {
  const practicedAt = entry.completedAt || entry.lastPracticedAt || entry.startedAt
  const clock = formatClock(practicedAt, locale)
  if (clock) return clock
  if (entry.completedAt) return tr('已完成', 'Completed')
  if (entry.lastPracticedAt) return tr('最近练习', 'Last practiced')
  if (entry.startedAt) return tr('已开始', 'Started')
  return tr('未记录时间', 'No time recorded')
}

function gradeKey(score?: number): string {
  if (score === undefined) return 'pending'
  if (score >= 90) return 'excellent'
  if (score >= 80) return 'good'
  if (score >= 70) return 'solid'
  return 'weak'
}

function entryTimestamp(entry: HistoryEntry): number {
  const raw = entry.completedAt || entry.lastPracticedAt || entry.startedAt
  if (!raw) return 0
  const time = new Date(raw).getTime()
  return Number.isFinite(time) ? time : 0
}

function scenarioMetadataFromSession(session: TrainingSessionDTO): {
  scenarioId?: string
  title: string
  description: string
  difficulty?: string
  category?: string
} {
  const metadata = asRecord(session.task_config.metadata)
  const scenarioTraining = asRecord(metadata?.scenario_training)
  const scenarioId = session.scenario_template_id || asString(scenarioTraining?.id)
  const card = getScenarioTrainingCardById(scenarioId)
  return {
    scenarioId: scenarioId || undefined,
    title: card?.title || asString(scenarioTraining?.title) || session.task_config.tech_stack[0] || session.task_config.role,
    description: card?.description || session.task_config.tech_stack[1] || session.task_config.category,
    difficulty: card?.difficulty || session.task_config.difficulty,
    category: card?.category || session.task_config.category,
  }
}

function progressEntry(
  scenarioId: string,
  item: ScenarioTrainingProgressItem,
): HistoryEntry {
  const card = getScenarioTrainingCardById(scenarioId)
  return {
    key: `progress:${scenarioId}:${item.trainingSessionId || 'local'}`,
    sessionId: item.trainingSessionId,
    scenarioId,
    title: card?.title || scenarioId,
    description: card?.description || '',
    difficulty: card?.difficulty,
    category: card?.category,
    status: item.status === 'completed'
      ? 'completed'
      : item.status === 'in_progress'
        ? 'in_progress'
        : item.status === 'failed'
          ? 'failed'
          : 'not_started',
    score: coerceScore(item.score),
    scoreStatus: item.scoreStatus,
    reportId: item.reportId,
    lastPracticedAt: item.lastPracticedAt,
    branchInfo: getTrainingConversationBranchInfo({
      progress: item,
    }) ?? undefined,
    source: 'progress',
  }
}

function buildHistoryEntries(
  sessions: TrainingSessionDTO[],
  progress: ScenarioTrainingProgress,
): HistoryEntry[] {
  const entries: HistoryEntry[] = []
  const bySessionId = new Map<string, HistoryEntry>()

  sessions.forEach((session) => {
    const metadata = scenarioMetadataFromSession(session)
    const matchingProgress = metadata.scenarioId
      ? progress[metadata.scenarioId]
      : undefined
    const progressForSession = matchingProgress?.trainingSessionId === session.session_id
      ? matchingProgress
      : undefined
    const entry: HistoryEntry = {
      key: `session:${session.session_id}`,
      sessionId: session.session_id,
      scenarioId: metadata.scenarioId,
      title: metadata.title,
      description: metadata.description,
      difficulty: metadata.difficulty,
      category: metadata.category,
      status: normalizeSessionStatus(session.status),
      score: coerceScore(progressForSession?.score),
      scoreStatus: progressForSession?.scoreStatus,
      reportId: session.report_id ? String(session.report_id) : progressForSession?.reportId,
      roomId: session.room_id,
      mode: session.mode,
      messageCount: session.message_count,
      startedAt: session.started_at,
      completedAt: session.completed_at,
      lastPracticedAt: progressForSession?.lastPracticedAt,
      branchInfo: getTrainingConversationBranchInfo({
        session,
        progress: progressForSession,
      }) ?? undefined,
      source: 'session',
    }
    entries.push(entry)
    bySessionId.set(session.session_id, entry)
  })

  Object.entries(progress).forEach(([scenarioId, item]) => {
    if (!item) return
    if (item.trainingSessionId && bySessionId.has(item.trainingSessionId)) {
      const entry = bySessionId.get(item.trainingSessionId)
      if (!entry) return
      entry.score = coerceScore(item.score) ?? entry.score
      entry.scoreStatus = item.scoreStatus ?? entry.scoreStatus
      entry.reportId = item.reportId ?? entry.reportId
      entry.lastPracticedAt = item.lastPracticedAt ?? entry.lastPracticedAt
      entry.branchInfo = entry.branchInfo ?? getTrainingConversationBranchInfo({
        progress: item,
      }) ?? undefined
      return
    }
    entries.push(progressEntry(scenarioId, item))
  })

  return entries.sort((a, b) => entryTimestamp(b) - entryTimestamp(a))
}

function matchesEntry(
  entry: HistoryEntry,
  query: string,
  scenarioFilter: string,
  statusFilter: StatusFilter,
): boolean {
  if (scenarioFilter !== 'all' && entry.scenarioId !== scenarioFilter) return false
  if (statusFilter !== 'all' && entry.status !== statusFilter) return false
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [
    entry.title,
    entry.description,
    entry.scenarioId,
    entry.sessionId,
    entry.category,
    entry.difficulty,
    entry.mode,
    entry.branchInfo?.branchId,
    entry.branchInfo?.forkPointMessageId,
    entry.branchInfo?.selectedTailMessageId,
    entry.branchInfo?.pathSummary,
    entry.branchInfo?.lastReplyPreview,
    getScenarioStatusLabel(entry.status, searchLabel),
  ].some((value) => String(value || '').toLowerCase().includes(needle))
}

export default function TrainingHistoryPage() {
  const { locale, t, tr } = useI18n()
  const { currentUser } = useAuthContext()
  const progressScope = useMemo(() => ({
    userId: currentUser?.userId ?? null,
    teamId: currentUser?.teamId ?? null,
  }), [currentUser?.teamId, currentUser?.userId])
  const [sessions, setSessions] = useState<TrainingSessionDTO[]>([])
  const [progress, setProgress] = useState<ScenarioTrainingProgress>(() => (
    getScenarioTrainingProgress(progressScope)
  ))
  const [loading, setLoading] = useState(true)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [progressError, setProgressError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [scenarioFilter, setScenarioFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  useEffect(() => {
    setProgress(getScenarioTrainingProgress(progressScope))
  }, [progressScope])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setSessionError(null)
    setProgressError(null)

    Promise.allSettled([
      listTrainingSessions({
        limit: 100,
        userId: progressScope.userId,
        teamId: progressScope.teamId,
      }),
      fetchScenarioTrainingProgress(progressScope),
    ])
      .then(([sessionResult, progressResult]) => {
        if (cancelled) return

        if (sessionResult.status === 'fulfilled') {
          setSessions(sessionResult.value)
        } else {
          setSessions([])
          setSessionError(getErrorMessage(sessionResult.reason, tr('训练会话加载失败。', 'Could not load training sessions.')))
        }

        if (progressResult.status === 'fulfilled') {
          setProgress((current) => {
            const merged = mergeScenarioTrainingProgressRecords(current, progressResult.value)
            saveScenarioTrainingProgress(merged, progressScope)
            return merged
          })
        } else {
          setProgressError(getErrorMessage(progressResult.reason, tr('场景进度同步失败。', 'Could not sync scenario progress.')))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [progressScope, tr])

  const entries = useMemo(() => buildHistoryEntries(sessions, progress), [progress, sessions])
  const scenarioOptions = useMemo(() => {
    const seen = new Map<string, string>()
    entries.forEach((entry) => {
      if (entry.scenarioId && !seen.has(entry.scenarioId)) {
        seen.set(entry.scenarioId, entry.title)
      }
    })
    return [...seen.entries()].map(([value, label]) => ({ value, label }))
  }, [entries])
  const filteredEntries = useMemo(
    () => entries.filter((entry) => matchesEntry(entry, query, scenarioFilter, statusFilter)),
    [entries, query, scenarioFilter, statusFilter],
  )
  const hasActiveFilters = Boolean(query.trim()) || scenarioFilter !== 'all' || statusFilter !== 'all'
  const selectedScenarioLabel = scenarioFilter === 'all'
    ? tr('全部场景', 'All scenarios')
    : scenarioOptions.find((option) => option.value === scenarioFilter)?.label ?? scenarioFilter
  const selectedStatusLabel = statusFilter === 'all'
    ? tr('全部状态', 'All statuses')
    : getScenarioStatusFilterLabel(statusFilter, tr)
  const filterCountText = hasActiveFilters
    ? tr('{filtered} / {total} 条', '{filtered} of {total} records', {
      filtered: filteredEntries.length,
      total: entries.length,
    })
    : tr('{count} 条', '{count} records', { count: entries.length })
  const resetFilters = () => {
    setQuery('')
    setScenarioFilter('all')
    setStatusFilter('all')
  }

  return (
    <PageShell width="wide" className="training-history-page">
      <PageHeader
        eyebrow={tr('训练记录', 'Training history')}
        icon={<History size={16} />}
        title={tr('训练历史', 'History')}
      />

      <section className="training-history-toolbar" aria-label={tr('训练记录筛选', 'Training history filters')}>
        <label className="training-history-search">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tr('搜索场景、会话、分类...', 'Search scenario, session, category...')}
          />
        </label>

        <label className="training-history-select">
          <FileText size={15} />
          <select
            value={scenarioFilter}
            onChange={(event) => setScenarioFilter(event.target.value)}
          >
            <option value="all">{tr('全部场景', 'All scenarios')}</option>
            {scenarioOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="training-history-select">
          <CheckCircle2 size={15} />
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
          >
            {statusOptions.map((option) => (
              <option key={option} value={option}>
                {getScenarioStatusFilterLabel(option, tr)}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="training-history-filter-summary" aria-label={tr('当前筛选', 'Current filters')}>
        <div>
          <span>{filterCountText}</span>
          {scenarioFilter !== 'all' && <strong>{selectedScenarioLabel}</strong>}
          {statusFilter !== 'all' && <strong>{selectedStatusLabel}</strong>}
          {query.trim() && <strong>{query.trim()}</strong>}
        </div>
        {hasActiveFilters && (
          <button type="button" onClick={resetFilters}>
            {tr('清空筛选', 'Clear filters')}
          </button>
        )}
      </section>

      {(sessionError || progressError) && (
        <section className="training-history-alerts">
          {sessionError && (
            <div>
              <AlertCircle size={15} />
              <span>{sessionError}</span>
            </div>
          )}
          {progressError && (
            <div>
              <AlertCircle size={15} />
              <span>{progressError}</span>
            </div>
          )}
        </section>
      )}

      <section className="training-history-list" aria-label={tr('训练记录列表', 'Training history records')}>
        <div className="training-history-list-head">
          <span>{tr('练习时间', 'Practice time')}</span>
          <span>{tr('场景', 'Scenario')}</span>
          <span>{tr('状态', 'Status')}</span>
          <span>{tr('分数', 'Score')}</span>
          <span>{tr('操作', 'Actions')}</span>
        </div>

        {loading && (
          <div className="training-history-loading">
            <Loader2 className="training-history-spin" size={20} />
            <span>{tr('正在加载训练记录...', 'Loading history...')}</span>
          </div>
        )}

        {!loading && filteredEntries.length === 0 && (
          <div className="training-history-empty">
            {entries.length === 0 ? <History size={24} /> : <Search size={24} />}
            <p>
              {entries.length === 0
                ? tr('还没有训练记录。', 'No training records yet.')
                : tr('没有匹配当前筛选的记录。', 'No records match the current filters.')}
            </p>
            <div className="training-history-empty-actions">
              {entries.length === 0 ? (
                <Link to={APP_ROUTES.practiceScenarios}>
                  <RotateCcw size={14} />
                  {tr('回到训练', 'Back to training')}
                </Link>
              ) : hasActiveFilters ? (
                <button type="button" onClick={resetFilters}>
                  {tr('清空筛选', 'Clear filters')}
                </button>
              ) : null}
            </div>
          </div>
        )}

        {!loading && filteredEntries.map((entry) => {
          const scoreClass = gradeKey(entry.score)
          const practicedAt = entry.completedAt || entry.lastPracticedAt || entry.startedAt
          const roomId = Number(entry.roomId)
          const chatPath = entry.sessionId && entry.mode && Number.isFinite(roomId) && roomId > 0
            ? buildTrainingModeChatPath(roomId, entry.mode, entry.sessionId)
            : null
          const branchSummary = entry.branchInfo ? historyBranchSummaryText(entry.branchInfo, tr) : ''
          return (
            <article className="training-history-row" key={entry.key}>
              <div className="training-history-time">
                <strong>{formatDate(practicedAt, locale, tr)}</strong>
                <span>{historyTimeContext(entry, locale, tr)}</span>
              </div>

              <div className="training-history-scenario">
                <div>
                  <strong>{entry.title}</strong>
                  <span>{historyEntryMetaText(entry, tr)}</span>
                </div>
                <div className="training-history-tags">
                  <span className={`training-history-source-tag ${entry.source}`}>
                    {translateLabel(sourceLabels[entry.source], tr)}
                  </span>
                  {entry.difficulty && (
                    <span>{translatedDifficulty(entry.difficulty, tr)}</span>
                  )}
                  {entry.category && (
                    <span>{translatedCategory(entry.category, tr)}</span>
                  )}
                  {entry.mode && <span>{translatedMode(entry.mode, t)}</span>}
                  {entry.branchInfo && (
                    <span
                      className="training-history-branch-tag"
                      title={historyBranchTitle(entry.branchInfo, tr)}
                    >
                      <GitBranch size={12} />
                      {historyBranchTagText(entry.branchInfo, tr)}
                    </span>
                  )}
                </div>
                {branchSummary && entry.branchInfo && (
                  <p
                    className={`training-history-branch-summary${entry.branchInfo.lastReplyPreview ? '' : ' empty'}`}
                    title={historyBranchTitle(entry.branchInfo, tr)}
                  >
                    <GitBranch size={12} />
                    <span>{branchSummary}</span>
                  </p>
                )}
              </div>

              <div>
                <span className={`training-history-status ${entry.status}`}>
                  {entry.status === 'completed' && <CheckCircle2 size={14} />}
                  {entry.status === 'in_progress' && <Clock3 size={14} />}
                  {entry.status === 'not_started' && <FileText size={14} />}
                  {entry.status === 'failed' && <AlertCircle size={14} />}
                  {getScenarioStatusLabel(entry.status, tr)}
                </span>
              </div>

              <div>
                <span className={`training-history-score ${scoreClass}`}>
                  <Trophy size={14} />
                  {entry.score === undefined
                    ? entry.scoreStatus === 'pending'
                      ? tr('评分中', 'Scoring')
                      : '--'
                    : `${entry.score}/100`}
                </span>
              </div>

              <div className="training-history-actions">
                {entry.sessionId ? (
                  <Link className="training-history-review-link" to={APP_ROUTES.reviewSession(entry.sessionId)}>
                    <FileText size={14} />
                    {tr('查看结果', 'View result')}
                  </Link>
                ) : (
                  <Link className="training-history-review-link" to={APP_ROUTES.practiceScenarios}>
                    <RotateCcw size={14} />
                    {tr('回到训练', 'Back to training')}
                  </Link>
                )}
                {chatPath && (
                  <Link
                    className="training-history-icon-link"
                    to={chatPath}
                    title={tr('打开聊天回放', 'Open chat replay')}
                    aria-label={tr('打开聊天回放', 'Open chat replay')}
                  >
                    <ExternalLink size={14} />
                  </Link>
                )}
              </div>
            </article>
          )
        })}
      </section>
    </PageShell>
  )
}
