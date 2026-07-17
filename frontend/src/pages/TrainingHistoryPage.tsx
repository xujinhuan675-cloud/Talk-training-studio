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
import { useI18n, type Locale, type TranslateInline } from '../i18n'
import {
  getScenarioTrainingCardById,
  getScenarioTrainingProgress,
  mergeScenarioTrainingProgressRecords,
  saveScenarioTrainingProgress,
  type ScenarioTrainingProgress,
  type ScenarioTrainingProgressItem,
} from '../data/trainingScenarios'
import './TrainingHistoryPage.css'

type HistoryStatus = 'not_started' | 'in_progress' | 'completed' | 'failed'
type StatusFilter = 'all' | HistoryStatus
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

const statusOptions: Array<{ value: StatusFilter; label: LocalizedText }> = [
  { value: 'all', label: ['全部状态', 'All statuses'] },
  { value: 'completed', label: ['已完成', 'Completed'] },
  { value: 'in_progress', label: ['进行中', 'In progress'] },
  { value: 'not_started', label: ['未开始', 'Not started'] },
  { value: 'failed', label: ['失败', 'Failed'] },
]

const statusLabels: Record<HistoryStatus, LocalizedText> = {
  not_started: ['未开始', 'Not started'],
  in_progress: ['进行中', 'In progress'],
  completed: ['已完成', 'Completed'],
  failed: ['失败', 'Failed'],
}

const difficultyLabels: Record<string, LocalizedText> = {
  easy: ['简单', 'Easy'],
  medium: ['中等', 'Medium'],
  hard: ['困难', 'Hard'],
  expert: ['专家', 'Expert'],
}

const categoryLabels: Record<string, LocalizedText> = {
  sales: ['销售', 'Sales'],
  customer_service: ['客服', 'Service'],
  negotiation: ['谈判', 'Negotiation'],
  interview: ['面试', 'Interview'],
  workplace: ['职场', 'Workplace'],
}

const modeLabels: Record<string, LocalizedText> = {
  text: ['文本', 'Text'],
  voice: ['语音', 'Voice'],
  video: ['视频', 'Video'],
  realtime: ['实时语音', 'Realtime'],
  live_coach: ['实时教练', 'Live coach'],
}

const sourceLabels: Record<HistoryEntry['source'], LocalizedText> = {
  session: ['训练会话', 'Session'],
  progress: ['本地进度', 'Local progress'],
}

function translateLabel(label: LocalizedText, tr: TranslateInline): string {
  return tr(label[0], label[1])
}

function translatedRecordLabel(
  labels: Record<string, LocalizedText>,
  value: string | undefined,
  tr: TranslateInline,
): string {
  if (!value) return ''
  const label = labels[value]
  return label ? translateLabel(label, tr) : value
}

function getErrorMessage(error: unknown, fallback = 'Request failed'): string {
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

function historyBranchSourceText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  if (info.source === 'session') return tr('metadata：会话', 'metadata: session')
  if (info.source === 'report') return tr('metadata：报告', 'metadata: report')
  return tr('metadata：进度', 'metadata: progress')
}

function historyBranchPathText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  const count = info.pathCount || info.selectedPath.length
  if (count > 0) return tr('当前路径：{count} 节点', 'Current path: {count} nodes', { count })
  if (info.selectedTailMessageId) return tr('当前路径：尾节点引用', 'Current path: tail ref')
  return tr('当前路径：分支引用', 'Current path: branch ref')
}

function historyBranchEmptyText(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  if (info.selectedPath.length > 0 && !info.selectedPath.some((item) => item.content.trim())) {
    return tr('metadata 只有消息 ID，没有保存最后回复正文。', 'Metadata has message IDs only; no last reply text was saved.')
  }
  return tr('metadata 没有保存可预览的路径正文。', 'Metadata has no previewable path text.')
}

function historyBranchTitle(info: TrainingConversationBranchInfo, tr: TranslateInline): string {
  return [
    historyBranchSourceText(info, tr),
    historyBranchPathText(info, tr),
    info.branchId ? tr('分支：{value}', 'Branch: {value}', { value: info.branchId }) : '',
    info.forkPointMessageId ? tr('分叉点：{value}', 'Fork point: {value}', { value: info.forkPointMessageId }) : '',
    info.selectedTailMessageId ? tr('尾节点：{value}', 'Tail: {value}', { value: info.selectedTailMessageId }) : '',
    info.pathSummary ? compactHistoryBranchText(info.pathSummary, 90) : '',
    info.lastReplyPreview ? tr('最后回复：{value}', 'Last reply: {value}', { value: compactHistoryBranchText(info.lastReplyPreview, 90) }) : '',
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
  if (!info.pathSummary) return historyBranchEmptyText(info, tr)
  if (info.forkPointMessageId) {
    return tr('分叉点：{value}', 'Fork point: {value}', {
      value: compactHistoryBranchText(info.forkPointMessageId, 48),
    })
  }
  if (info.pathSummary) return compactHistoryBranchText(info.pathSummary, 72)
  if (info.selectedTailMessageId) {
    return tr('尾节点：{value}', 'Tail: {value}', {
      value: compactHistoryBranchText(info.selectedTailMessageId, 48),
    })
  }
  return ''
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
    statusLabels[entry.status].join(' '),
  ].some((value) => String(value || '').toLowerCase().includes(needle))
}

export default function TrainingHistoryPage() {
  const { locale, tr } = useI18n()
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
  const completedCount = entries.filter((entry) => entry.status === 'completed').length
  const scoredEntries = entries.filter((entry) => entry.score !== undefined)
  const averageScore = scoredEntries.length
    ? Math.round(scoredEntries.reduce((sum, entry) => sum + (entry.score ?? 0), 0) / scoredEntries.length)
    : undefined

  return (
    <div className="training-history-page">
      <header className="training-history-hero">
        <div className="training-history-title-block">
          <div className="training-history-kicker">
            <History size={16} />
            <span>{tr('训练记录', 'Training history')}</span>
          </div>
          <h1>{tr('复盘场景练习结果', 'Review scenario practice results')}</h1>
          <p>
            {tr(
              '按场景、状态或关键词筛选已完成和进行中的练习。结果复用训练会话、复盘报告和本地场景进度。',
              'Filter completed and in-progress drills by scenario, status, or keyword. Results reuse Training Session records, reports, and local scenario progress.',
            )}
          </p>
        </div>

        <div className="training-history-summary" aria-label={tr('训练记录概览', 'Training history summary')}>
          <div>
            <span>{entries.length}</span>
            <small>{tr('总记录', 'Total records')}</small>
          </div>
          <div>
            <span>{completedCount}</span>
            <small>{tr('已完成', 'Completed')}</small>
          </div>
          <div>
            <span>{averageScore ?? '--'}</span>
            <small>{tr('平均分', 'Average score')}</small>
          </div>
        </div>
      </header>

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
              <option key={option.value} value={option.value}>
                {translateLabel(option.label, tr)}
              </option>
            ))}
          </select>
        </label>
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
          <span>{tr('回放', 'Replay')}</span>
        </div>

        {loading && (
          <div className="training-history-loading">
            <Loader2 className="training-history-spin" size={20} />
            <span>{tr('正在加载训练记录...', 'Loading history...')}</span>
          </div>
        )}

        {!loading && filteredEntries.length === 0 && (
          <div className="training-history-empty">
            <Search size={24} />
            <p>{tr('没有匹配的训练记录。', 'No matching training records.')}</p>
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
                <span>{formatClock(practicedAt, locale) || translateLabel(sourceLabels[entry.source], tr)}</span>
              </div>

              <div className="training-history-scenario">
                <div>
                  <strong>{entry.title}</strong>
                  <span>{entry.description || entry.sessionId || tr('本地进度记录', 'Local progress record')}</span>
                </div>
                <div className="training-history-tags">
                  {entry.difficulty && (
                    <span>{translatedRecordLabel(difficultyLabels, entry.difficulty, tr)}</span>
                  )}
                  {entry.category && (
                    <span>{translatedRecordLabel(categoryLabels, entry.category, tr)}</span>
                  )}
                  {entry.mode && <span>{translatedRecordLabel(modeLabels, entry.mode, tr)}</span>}
                  {entry.branchInfo && (
                    <span
                      className="training-history-branch-tag"
                      title={historyBranchTitle(entry.branchInfo, tr)}
                    >
                      <GitBranch size={12} />
                      {historyBranchTagText(entry.branchInfo, tr)}
                    </span>
                  )}
                  {entry.branchInfo && (
                    <span
                      className="training-history-branch-source-tag"
                      title={historyBranchTitle(entry.branchInfo, tr)}
                    >
                      {historyBranchSourceText(entry.branchInfo, tr)}
                    </span>
                  )}
                </div>
                {entry.branchInfo && (
                  <div
                    className="training-history-branch-context"
                    title={historyBranchTitle(entry.branchInfo, tr)}
                  >
                    <span>{historyBranchPathText(entry.branchInfo, tr)}</span>
                    {entry.branchInfo.forkPointMessageId && (
                      <span>
                        {tr('分叉点：{value}', 'Fork point: {value}', {
                          value: compactHistoryBranchText(entry.branchInfo.forkPointMessageId, 34),
                        })}
                      </span>
                    )}
                    {entry.branchInfo.selectedTailMessageId && (
                      <span>
                        {tr('尾节点：{value}', 'Tail: {value}', {
                          value: compactHistoryBranchText(entry.branchInfo.selectedTailMessageId, 34),
                        })}
                      </span>
                    )}
                  </div>
                )}
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
                  {translateLabel(statusLabels[entry.status], tr)}
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
                  <Link to={`/training-result/${encodeURIComponent(entry.sessionId)}`}>
                    {tr('结果', 'Result')}
                  </Link>
                ) : (
                  <span>{tr('无会话', 'No session')}</span>
                )}
                {chatPath && (
                  <Link to={chatPath} title={tr('打开聊天回放', 'Open chat replay')} aria-label={tr('打开聊天回放', 'Open chat replay')}>
                    <ExternalLink size={14} />
                  </Link>
                )}
              </div>
            </article>
          )
        })}
      </section>
    </div>
  )
}
