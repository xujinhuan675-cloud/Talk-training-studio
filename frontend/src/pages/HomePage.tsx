import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  ChevronRight,
  Loader2,
  Play,
  Swords,
  TrendingUp,
} from 'lucide-react'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n, type TranslateInline } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { fetchScenarioTrainingCatalog, fetchScenarioTrainingProgress } from '../services/scenarioTraining'
import { launchScenarioTraining } from '../services/scenarioTrainingLaunch'
import {
  getScenarioTrainingCardById,
  getScenarioTrainingProgress,
  mergeScenarioTrainingProgress,
  mergeScenarioTrainingProgressRecords,
  saveScenarioTrainingProgress,
  scenarioTrainingCatalog,
  type ScenarioTrainingCard,
  type ScenarioTrainingProgress,
} from '../data/trainingScenarios'
import { getScenarioCategoryLabel, getScenarioDifficultyLabel } from '../utils/scenarioLabels'
import {
  listTrainingSessions,
  type TrainingSessionDTO,
  type TrainingSessionStatus,
} from '../services/trainingSession'
import {
  buildTrainingModeChatPath,
  type InteractionMode,
  type TrainingProfile,
} from '../services/trainingMode'
import { useGrowth } from '../hooks/useGrowth'
import { getErrorMessage } from '../utils/errors'
import { Badge, type BadgeTone } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { PageHeader, PageSection, PageShell } from '../components/ui/page'
import { StateBlock, StateSpinner } from '../components/ui/state'
import { Surface } from '../components/ui/surface'
import './HomePage.css'

const AVATAR_COLORS = ['#0F766E', '#334155', '#2563EB', '#475569', '#6366F1', '#0B5F59']

function getAvatarColor(id: string | number): string {
  const hash = String(id).split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}

function difficultyTone(difficulty: ScenarioTrainingCard['difficulty']): BadgeTone {
  if (difficulty === 'easy') return 'success'
  if (difficulty === 'medium') return 'warning'
  if (difficulty === 'hard') return 'danger'
  return 'accent'
}

function getInitial(name: string): string {
  return name.trim().charAt(0) || '?'
}

function timeAgo(dateStr: string | null, tr: TranslateInline): string {
  if (!dateStr) return ''
  const then = new Date(dateStr).getTime()
  if (Number.isNaN(then)) return ''
  const minutes = Math.floor((Date.now() - then) / 60000)
  if (minutes < 1) return tr('刚刚', 'Just now')
  if (minutes < 60) return tr('{count} 分钟前', '{count} min ago', { count: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return tr('{count} 小时前', '{count} hr ago', { count: hours })
  const days = Math.floor(hours / 24)
  if (days === 1) return tr('昨天', 'Yesterday')
  if (days < 30) return tr('{count} 天前', '{count} days ago', { count: days })
  return tr('{count} 个月前', '{count} months ago', { count: Math.floor(days / 30) })
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function sessionTimestamp(session: TrainingSessionDTO): number {
  const raw = session.completed_at || session.started_at
  if (!raw) return 0
  const time = new Date(raw).getTime()
  return Number.isFinite(time) ? time : 0
}

function sessionTime(session: TrainingSessionDTO): string | null {
  return session.completed_at || session.started_at || null
}

function sessionTitle(session: TrainingSessionDTO, tr: TranslateInline): string {
  const metadata = asRecord(session.task_config.metadata)
  const scenarioTraining = asRecord(metadata?.scenario_training)
  const card = getScenarioTrainingCardById(session.scenario_template_id || cleanText(scenarioTraining?.id))
  return card?.title
    || cleanText(scenarioTraining?.title)
    || cleanText(session.task_config.tech_stack?.[0])
    || cleanText(session.task_config.role)
    || tr('训练会话', 'Training session')
}

function trainingModeLabel(session: TrainingSessionDTO, tr: TranslateInline): string {
  if (session.mode === 'text') return tr('文字', 'Text')
  if (session.mode === 'voice') return tr('语音', 'Voice')
  if (session.mode === 'video') return tr('视频', 'Video')
  return session.mode
}

function statusLabel(status: TrainingSessionStatus, tr: TranslateInline): string {
  if (status === 'completed') return tr('已完成', 'Completed')
  if (status === 'failed') return tr('失败', 'Failed')
  if (status === 'created') return tr('待开始', 'Ready')
  return tr('进行中', 'In progress')
}

function resolveInteractionMode(session: TrainingSessionDTO): InteractionMode {
  const sessionMetadata = asRecord(session.metadata)
  const taskMetadata = asRecord(session.task_config.metadata)
  const scenarioTraining = asRecord(taskMetadata?.scenario_training)
  const candidates = [
    sessionMetadata?.interactionMode,
    sessionMetadata?.interaction_mode,
    taskMetadata?.interactionMode,
    taskMetadata?.interaction_mode,
    scenarioTraining?.interactionMode,
    scenarioTraining?.interaction_mode,
  ]
  if (candidates.some((value) => value === 'realtime')) return 'realtime'
  return 'turn_based'
}

function resolveTrainingProfile(session: TrainingSessionDTO): TrainingProfile | null {
  const sessionMetadata = asRecord(session.metadata)
  const taskMetadata = asRecord(session.task_config.metadata)
  const candidates = [
    sessionMetadata?.trainingProfile,
    sessionMetadata?.training_profile,
    taskMetadata?.trainingProfile,
    taskMetadata?.training_profile,
  ]
  return candidates.some((value) => value === 'live_coach') ? 'live_coach' : null
}

function resolveLiveCoachLanguage(session: TrainingSessionDTO, key: 'sourceLanguage' | 'targetLanguage'): string | null {
  const sessionMetadata = asRecord(session.metadata)
  const taskMetadata = asRecord(session.task_config.metadata)
  const liveCoach = asRecord(taskMetadata?.liveCoach)
  const snakeKey = key === 'sourceLanguage' ? 'source_language' : 'target_language'
  return cleanText(liveCoach?.[key])
    || cleanText(liveCoach?.[snakeKey])
    || cleanText(taskMetadata?.[key])
    || cleanText(taskMetadata?.[snakeKey])
    || cleanText(sessionMetadata?.[key])
    || cleanText(sessionMetadata?.[snakeKey])
    || null
}

function resolveReplyLanguage(session: TrainingSessionDTO): string | null {
  const sessionMetadata = asRecord(session.metadata)
  const taskMetadata = asRecord(session.task_config.metadata)
  const scenarioTraining = asRecord(taskMetadata?.scenario_training)
  const language = asRecord(taskMetadata?.language)
  const candidates = [
    taskMetadata?.replyLanguage,
    taskMetadata?.reply_language,
    scenarioTraining?.replyLanguage,
    scenarioTraining?.reply_language,
    language?.replyLanguage,
    language?.reply_language,
    sessionMetadata?.replyLanguage,
    sessionMetadata?.reply_language,
  ]
  for (const candidate of candidates) {
    const text = cleanText(candidate)
    if (text) return text
  }
  return null
}

function isContinuableSession(session: TrainingSessionDTO): boolean {
  return session.status !== 'completed'
    && session.status !== 'failed'
    && Boolean(cleanText(session.room_id))
}

function sessionPath(session: TrainingSessionDTO): string {
  if (isContinuableSession(session) && session.room_id) {
    return buildTrainingModeChatPath(
      session.room_id,
      session.mode,
      session.session_id,
      resolveInteractionMode(session),
      {
        trainingProfile: resolveTrainingProfile(session),
        replyLanguage: resolveReplyLanguage(session),
        sourceLanguage: resolveLiveCoachLanguage(session, 'sourceLanguage'),
        targetLanguage: resolveLiveCoachLanguage(session, 'targetLanguage'),
      },
    )
  }
  return APP_ROUTES.reviewSession(session.session_id)
}

function xpProgressText(currentXP: number, nextLevelXP: number | null, tr: TranslateInline): string {
  if (nextLevelXP === null) return tr('{xp} XP · 已达最高等级', '{xp} XP · max level', { xp: currentXP })
  return tr('{xp} / {next} XP', '{xp} / {next} XP', {
    xp: currentXP,
    next: nextLevelXP,
  })
}

function scenarioTimestamp(value?: string): number {
  if (!value) return 0
  const time = new Date(value).getTime()
  return Number.isFinite(time) ? time : 0
}

function scenarioRecommendationPriority(scenario: ScenarioTrainingCard): number {
  if (scenario.status === 'in_progress') return 0
  if (scenario.required && scenario.status === 'not_started') return 1
  if (scenario.status === 'not_started') return 2
  if (scenario.status === 'failed') return 3
  if (typeof scenario.score === 'number' && scenario.score < 80) return 4
  return 5
}

function getRecommendedScenarios(scenarios: ScenarioTrainingCard[]): ScenarioTrainingCard[] {
  return [...scenarios]
    .sort((a, b) => (
      scenarioRecommendationPriority(a) - scenarioRecommendationPriority(b)
      || Number(b.required) - Number(a.required)
      || scenarioTimestamp(a.lastPracticedAt) - scenarioTimestamp(b.lastPracticedAt)
      || a.title.localeCompare(b.title)
    ))
    .slice(0, 1)
}

function recommendationReason(scenario: ScenarioTrainingCard, tr: TranslateInline): string {
  if (scenario.status === 'in_progress') return tr('继续进行中的训练', 'Continue an active practice')
  if (scenario.required && scenario.status === 'not_started') return tr('必练场景，建议先完成', 'Required scenario to finish first')
  if (scenario.status === 'failed') return tr('上次未通过，适合补练', 'Recovery practice after a failed run')
  if (typeof scenario.score === 'number' && scenario.score < 80) return tr('分数还有提升空间', 'Score has room to improve')
  return tr('适合直接热身', 'Good warm-up scenario')
}

const HomePage: React.FC = () => {
  const navigate = useNavigate()
  const { currentUser, requireAuthenticated } = useAuthContext()
  const { tr, t } = useI18n()
  const [sessions, setSessions] = useState<TrainingSessionDTO[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const {
    loading: growthLoading,
    levelInfo,
  } = useGrowth()
  const progressScope = useMemo(() => ({
    userId: currentUser?.userId ?? null,
    teamId: currentUser?.teamId ?? null,
  }), [currentUser?.teamId, currentUser?.userId])
  const [catalog, setCatalog] = useState<ScenarioTrainingCard[]>(scenarioTrainingCatalog)
  const [progress, setProgress] = useState<ScenarioTrainingProgress>(() => (
    getScenarioTrainingProgress(progressScope)
  ))
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null)
  const [scenarioLaunchError, setScenarioLaunchError] = useState<string | null>(null)

  useEffect(() => {
    setProgress(getScenarioTrainingProgress(progressScope))
  }, [progressScope])

  useEffect(() => {
    let cancelled = false

    fetchScenarioTrainingCatalog()
      .then((templates) => {
        if (cancelled) return
        if (templates.length > 0) setCatalog(templates)
      })
      .catch(() => {
        if (!cancelled) setCatalog(scenarioTrainingCatalog)
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    fetchScenarioTrainingProgress(progressScope)
      .then((remoteProgress) => {
        if (cancelled) return
        setProgress((current) => {
          const merged = mergeScenarioTrainingProgressRecords(current, remoteProgress)
          saveScenarioTrainingProgress(merged, progressScope)
          return merged
        })
      })
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [progressScope])

  useEffect(() => {
    let cancelled = false
    setSessionsLoading(true)
    listTrainingSessions({
      limit: 5,
      userId: progressScope.userId,
      teamId: progressScope.teamId,
    })
      .then((data) => {
        if (cancelled) return
        setSessions([...data].sort((a, b) => sessionTimestamp(b) - sessionTimestamp(a)))
      })
      .catch(() => {
        if (!cancelled) setSessions([])
      })
      .finally(() => {
        if (!cancelled) setSessionsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [progressScope])

  const scenarios = useMemo(
    () => mergeScenarioTrainingProgress(catalog, progress),
    [catalog, progress],
  )
  const recommendedScenarios = useMemo(
    () => getRecommendedScenarios(scenarios),
    [scenarios],
  )
  const recentSessions = sessions.slice(0, 3)
  const growthLevelText = growthLoading ? '--' : tr('Lv.{level}', 'Lv.{level}', { level: levelInfo.level })
  const growthXpText = growthLoading
    ? t('common.loading')
    : xpProgressText(levelInfo.currentXP, levelInfo.nextLevelXP, tr)
  const growthProgress = growthLoading ? 0 : Math.round(levelInfo.progress * 100)

  const startRecommendedScenario = async (scenario: ScenarioTrainingCard) => {
    if (startingScenarioId !== null) return
    if (!requireAuthenticated()) return
    setStartingScenarioId(scenario.id)
    setScenarioLaunchError(null)
    try {
      await launchScenarioTraining({
        scenario,
        progress,
        progressScope,
        navigate,
        onProgressChange: setProgress,
      })
    } catch (error: unknown) {
      setScenarioLaunchError(getErrorMessage(error, tr('启动训练失败', 'Failed to start training')))
      setStartingScenarioId(null)
    }
  }

  return (
    <PageShell className="home-page">
      <PageHeader
        title={t('nav.home')}
        description={tr(
          '从推荐场景、快速备战和最近训练快速进入练习闭环。',
          'Start from recommendations, quick prep, recent sessions, reviews, and growth.',
        )}
      />

      <div className="home-main-stack">
        <div className="home-workflow-stack">
          <Surface className="home-start-panel" variant="accent" padding="lg">
            <div className="home-start-header">
              <div className="home-start-copy">
                <h2>{t('common.startTraining')}</h2>
                <p>
                  {tr(
                    '先从推荐场景立即开始；需要临场准备时，直接进入紧急备战。',
                    'Start from the recommended scenario, or use battle prep for an urgent conversation.',
                  )}
                </p>
              </div>

              <Link to={APP_ROUTES.growth} className="home-start-growth" aria-label={t('nav.growth')}>
                <span className="home-start-growth-icon" aria-hidden="true">
                  <TrendingUp size={16} />
                </span>
                <span className="home-start-growth-copy">
                  <strong>{growthLevelText}</strong>
                  <em>{growthXpText}</em>
                  <span className="home-start-growth-meter" aria-hidden="true">
                    <span style={{ width: `${growthProgress}%` }} />
                  </span>
                </span>
                <ChevronRight size={15} />
              </Link>
            </div>

            {scenarioLaunchError && (
              <div className="home-scenario-error" role="alert">
                <AlertCircle size={15} />
                <span>{scenarioLaunchError}</span>
              </div>
            )}

            <section className="home-recommendations" aria-label={tr('推荐训练场景', 'Recommended training scenarios')}>
              <div className="home-recommendation-head">
                <span>{tr('推荐下一场训练', 'Recommended next practice')}</span>
                <em>{tr('根据进度优先继续、必练或补练', 'Prioritizes active, required, or recovery practice')}</em>
              </div>

              <div className="home-recommendation-grid">
                {recommendedScenarios.map((scenario) => {
                  const starting = startingScenarioId === scenario.id
                  return (
                    <article className="home-scenario-option" key={scenario.id}>
                      <div className="home-scenario-body">
                        <div className="home-scenario-meta">
                          <Badge tone={difficultyTone(scenario.difficulty)} className={`difficulty ${scenario.difficulty}`}>
                            {getScenarioDifficultyLabel(scenario.difficulty, tr)}
                          </Badge>
                          <Badge tone="neutral">{getScenarioCategoryLabel(scenario.category, tr)}</Badge>
                          {scenario.required && (
                            <Badge tone="danger" className="required">{tr('必练', 'Required')}</Badge>
                          )}
                        </div>
                        <h3>{scenario.title}</h3>
                        <p>{scenario.description}</p>
                        <div className="home-scenario-reason">{recommendationReason(scenario, tr)}</div>
                      </div>
                      <div className="home-scenario-actions">
                        <Button
                          type="button"
                          variant="primary"
                          size="sm"
                          className="home-scenario-start"
                          onClick={() => void startRecommendedScenario(scenario)}
                          disabled={startingScenarioId !== null}
                        >
                          {starting ? <Loader2 size={15} className="home-scenario-spin" /> : <Play size={15} />}
                          {starting ? t('common.starting') : tr('立即开始', 'Start now')}
                        </Button>
                        <Button asChild variant="secondary" size="sm" className="home-scenario-prep">
                          <Link to={APP_ROUTES.practiceBattle}>
                            <Swords size={15} />
                            {tr('快速备战', 'Quick prep')}
                          </Link>
                        </Button>
                      </div>
                    </article>
                  )
                })}
              </div>
            </section>
          </Surface>

          <PageSection
            className="home-recent-section"
            title={tr('最近训练', 'Recent training')}
            actions={(
              <Button asChild variant="ghost" size="sm">
                <Link to={APP_ROUTES.reviewSessions}>
                  {t('nav.review')}
                  <ChevronRight size={14} />
                </Link>
              </Button>
            )}
          >
            <Surface className="home-recent-surface" padding="sm">
              {recentSessions.length === 0 ? (
                <StateBlock
                  className="home-empty-block"
                  icon={sessionsLoading ? <StateSpinner /> : undefined}
                  size="sm"
                  title={sessionsLoading ? t('common.loading') : tr('暂无训练记录', 'No training records yet')}
                  tone={sessionsLoading ? 'loading' : 'neutral'}
                />
              ) : (
                <div className="home-recent-list">
                  {recentSessions.map((session) => {
                    const title = sessionTitle(session, tr)
                    const initial = getInitial(title)
                    const color = getAvatarColor(session.session_id)
                    return (
                      <Link key={session.session_id} to={sessionPath(session)} className="home-recent-item">
                        <span className="home-recent-avatar" style={{ backgroundColor: color }}>
                          {initial}
                        </span>
                        <span className="home-recent-copy">
                          <strong>{title}</strong>
                          <em>
                            {statusLabel(session.status, tr)}
                            {' · '}
                            {trainingModeLabel(session, tr)}
                            {' · '}
                            {timeAgo(sessionTime(session), tr) || tr('未记录时间', 'No time')}
                          </em>
                        </span>
                        <ChevronRight size={15} />
                      </Link>
                    )
                  })}
                </div>
              )}
            </Surface>
          </PageSection>
        </div>
      </div>
    </PageShell>
  )
}

export default HomePage
