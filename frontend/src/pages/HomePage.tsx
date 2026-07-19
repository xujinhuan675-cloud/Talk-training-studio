import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronRight,
  ClipboardList,
  History,
  Play,
  Settings,
  SlidersHorizontal,
  Target,
  TrendingUp,
} from 'lucide-react'
import { useAuthContext } from '../contexts/AuthContext'
import { MANAGEMENT_SYSTEM_ROLES } from '../services/auth'
import { useI18n, type TranslateInline } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { getScenarioTrainingCardById } from '../data/trainingScenarios'
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
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { PageHeader, PageSection, PageShell } from '../components/ui/page'
import { Surface } from '../components/ui/surface'
import './HomePage.css'

const AVATAR_COLORS = ['#0F766E', '#334155', '#2563EB', '#475569', '#6366F1', '#0B5F59']

function getAvatarColor(id: string | number): string {
  const hash = String(id).split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
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
        sourceLanguage: resolveLiveCoachLanguage(session, 'sourceLanguage'),
        targetLanguage: resolveLiveCoachLanguage(session, 'targetLanguage'),
      },
    )
  }
  return APP_ROUTES.reviewSession(session.session_id)
}

const HomePage: React.FC = () => {
  const { currentUser, hasAnySystemRole } = useAuthContext()
  const { tr, t } = useI18n()
  const [sessions, setSessions] = useState<TrainingSessionDTO[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setSessionsLoading(true)
    listTrainingSessions({
      limit: 5,
      userId: currentUser?.userId ?? null,
      teamId: currentUser?.teamId ?? null,
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
  }, [currentUser?.teamId, currentUser?.userId])

  const recentSessions = sessions.slice(0, 3)
  const latestSession = recentSessions[0]
  const canUseManagementActions = hasAnySystemRole(MANAGEMENT_SYSTEM_ROLES)

  const quickLinks = [
    {
      to: APP_ROUTES.reviewSessions,
      icon: <History size={16} />,
      label: t('nav.review'),
    },
    {
      to: APP_ROUTES.growth,
      icon: <TrendingUp size={16} />,
      label: t('nav.growth'),
    },
    ...(canUseManagementActions
      ? [
          {
            to: APP_ROUTES.config,
            icon: <Settings size={16} />,
            label: t('nav.config'),
          },
        ]
      : []),
  ]

  return (
    <PageShell className="home-page" width="wide">
      <PageHeader
        icon={<Target size={16} />}
        eyebrow={t('nav.home')}
        title={tr('训练工作台', 'Training workbench')}
      />

      <div className="home-main-grid">
        <Surface className="home-start-panel" variant="accent" padding="lg">
          <div className="home-start-copy">
            <Badge tone="success">{tr('主流程', 'Primary flow')}</Badge>
            <h2>{t('common.startTraining')}</h2>
          </div>

          <div className="home-start-actions">
            <Button asChild variant="primary" className="home-start-button">
              <Link to={APP_ROUTES.practiceScenarios}>
                <Play size={16} />
                {t('nav.scenarioTraining')}
              </Link>
            </Button>
            {canUseManagementActions && (
              <Button asChild variant="secondary">
                <Link to={APP_ROUTES.practiceCustom}>
                  <SlidersHorizontal size={16} />
                  {t('nav.trainingStudio')}
                </Link>
              </Button>
            )}
          </div>

          {latestSession ? (
            <Link to={sessionPath(latestSession)} className="home-continue-link">
              <span className="home-continue-icon" aria-hidden="true">
                <ClipboardList size={15} />
              </span>
              <span className="home-continue-copy">
                <strong>
                  {isContinuableSession(latestSession)
                    ? tr('继续最近训练', 'Continue latest training')
                    : tr('查看最近训练结果', 'View latest training result')}
                </strong>
                <em>{sessionTitle(latestSession, tr)} · {timeAgo(sessionTime(latestSession), tr) || tr('未记录时间', 'No time')}</em>
              </span>
              <ChevronRight size={15} />
            </Link>
          ) : (
            <div className="home-continue-link is-empty">
              <span className="home-continue-icon" aria-hidden="true">
                <ClipboardList size={15} />
              </span>
              <span className="home-continue-copy">
                <strong>{sessionsLoading ? t('common.loading') : tr('暂无训练记录', 'No training records yet')}</strong>
                <em>{tr('从训练目录开始', 'Start from the catalog')}</em>
              </span>
            </div>
          )}
        </Surface>

        <div className="home-side-stack">
          <PageSection className="home-quick-section" title={tr('训练后', 'After training')}>
            <Surface className="home-link-surface" padding="sm">
              <div className="home-link-list">
                {quickLinks.map((item) => (
                  <Link
                    key={item.to}
                    to={item.to}
                    className="home-link-item"
                    aria-label={item.label}
                  >
                    <span className="home-link-icon" aria-hidden="true">
                      {item.icon}
                    </span>
                    <span className="home-link-copy">
                      <strong>{item.label}</strong>
                    </span>
                    <ChevronRight size={15} />
                  </Link>
                ))}
              </div>
            </Surface>
          </PageSection>

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
                <div className="home-empty-block">
                  <p>{sessionsLoading ? t('common.loading') : tr('暂无训练记录', 'No training records yet')}</p>
                </div>
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
