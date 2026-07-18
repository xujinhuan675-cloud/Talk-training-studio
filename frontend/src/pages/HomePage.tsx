import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Check,
  ChevronRight,
  ClipboardList,
  FileText,
  History,
  Loader2,
  Lock,
  MessageSquare,
  Swords,
  Target,
  TrendingUp,
} from 'lucide-react'
import { useAppContext } from '../contexts/AppContext'
import { useAuthContext } from '../contexts/AuthContext'
import { fetchRooms, startBattle, type ChatRoom } from '../services/api'
import { MANAGEMENT_SYSTEM_ROLES } from '../services/auth'
import {
  buildTrainingSessionStartRequest,
  createTrainingSession,
  startTrainingSession,
} from '../services/trainingSession'
import { buildTrainingModeChatPath } from '../services/trainingMode'
import { launchTrainingSessionFlow } from '../services/trainingLaunch'
import {
  buildScenarioTrainingBattlePayload,
  buildScenarioTrainingRouteState,
  buildScenarioTrainingTaskConfig,
  getScenarioTrainingCardById,
  getScenarioTrainingProgress,
  markScenarioTrainingStarted,
  saveScenarioTrainingProgress,
} from '../data/trainingScenarios'
import { useI18n, type TranslateInline } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { PageHeader, PageSection, PageShell, PageStatGrid } from '../components/ui/page'
import { Surface } from '../components/ui/surface'
import './HomePage.css'

const AVATAR_COLORS = ['#8B5226', '#1E3A5F', '#3D2E5C', '#6B4226', '#2E4A3F', '#4A3060']

function getAvatarColor(id: string | number): string {
  const hash = String(id).split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}

function getInitial(name: string): string {
  return name.charAt(0)
}

function formatXp(value: number, tr: TranslateInline): string {
  return tr('+{count} 经验', '+{count} XP', { count: value })
}

function timeAgo(dateStr: string | null, tr: TranslateInline): string {
  if (!dateStr) return ''
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  if (Number.isNaN(then)) return ''
  const diffMs = now - then
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return tr('刚刚', 'Just now')
  if (minutes < 60) return tr('{count} 分钟前', '{count} min ago', { count: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return tr('{count} 小时前', '{count} hr ago', { count: hours })
  const days = Math.floor(hours / 24)
  if (days === 1) return tr('昨天', 'Yesterday')
  if (days < 30) return tr('{count} 天前', '{count} days ago', { count: days })
  return tr('{count} 个月前', '{count} months ago', { count: Math.floor(days / 30) })
}

const dailyChallenge = {
  scenarioId: 'daily-upward-results-report',
  titleZh: '向上今日成果汇报',
  titleEn: 'Report Quarterly Results Upward',
  progress: 0.35,
  xp: 100,
}

interface SkillNode {
  labelZh: string
  labelEn: string
  status: 'done' | 'current' | 'locked'
}

const skillNodes: SkillNode[] = [
  { labelZh: '入门对话', labelEn: 'Conversation Basics', status: 'done' },
  { labelZh: '情绪管理', labelEn: 'Emotion Management', status: 'done' },
  { labelZh: '向上管理', labelEn: 'Managing Up', status: 'current' },
  { labelZh: '高层博弈', labelEn: 'Executive Influence', status: 'locked' },
  { labelZh: '危机处理', labelEn: 'Crisis Handling', status: 'locked' },
]

const HomePage: React.FC = () => {
  const navigate = useNavigate()
  const { personaMap } = useAppContext()
  const { currentUser, hasAnySystemRole } = useAuthContext()
  const { tr, t } = useI18n()
  const [rooms, setRooms] = useState<ChatRoom[]>([])
  const [dailyStarting, setDailyStarting] = useState(false)
  const [dailyError, setDailyError] = useState<string | null>(null)

  useEffect(() => {
    fetchRooms()
      .then((data) => {
        const sorted = data
          .filter((room) => room.type !== 'battle_prep')
          .sort((a, b) => {
            const ta = a.last_message_at ? new Date(a.last_message_at).getTime() : 0
            const tb = b.last_message_at ? new Date(b.last_message_at).getTime() : 0
            return tb - ta
          })
        setRooms(sorted)
      })
      .catch(() => {})
  }, [])

  const recentRooms = rooms.slice(0, 4)
  const latestRoom = recentRooms[0]
  const canUseManagementActions = hasAnySystemRole(MANAGEMENT_SYSTEM_ROLES)
  const dailyProgressPercent = Math.round(dailyChallenge.progress * 100)
  const dailyXpLabel = formatXp(dailyChallenge.xp, tr)
  const operatorLabel = currentUser?.teamName ?? currentUser?.name ?? tr('模拟用户', 'Mock user')
  const dailyStatusLabel = dailyStarting ? tr('启动中', 'Starting') : tr('可开始', 'Ready')
  const latestRoomTime = latestRoom
    ? (timeAgo(latestRoom.last_message_at, tr) || tr('暂无时间', 'No time'))
    : tr('没有可继续的对话', 'No active conversation')

  const startDailyChallenge = async () => {
    const scenario = getScenarioTrainingCardById(dailyChallenge.scenarioId)
    if (!scenario) {
      setDailyError(tr('今日挑战场景暂不可用', 'Today\'s challenge is unavailable'))
      return
    }

    const trainingMode = 'text'
    const interactionMode = 'turn_based'
    const progressScope = {
      userId: currentUser?.userId ?? null,
      teamId: currentUser?.teamId ?? null,
    }

    setDailyStarting(true)
    setDailyError(null)
    try {
      const useConversationMessageTreeRuntime = trainingMode === 'text' && interactionMode === 'turn_based'
      const progress = getScenarioTrainingProgress(progressScope)
      const scenarioParam = `scenarioTrainingId=${encodeURIComponent(scenario.id)}`
      await launchTrainingSessionFlow({
        createTrainingSessionRequest: {
          mode: trainingMode,
          scenario_template_id: scenario.id,
          user_id: progressScope.userId,
          team_id: progressScope.teamId,
          task_config: buildScenarioTrainingTaskConfig(scenario),
        },
        createTrainingSession,
        battlePayload: useConversationMessageTreeRuntime
          ? null
          : buildScenarioTrainingBattlePayload(scenario, trainingMode),
        startBattle,
        buildTrainingSessionStartRequest,
        startTrainingSession,
        trainingMode,
        interactionMode,
        buildChatPath: (roomId, nextTrainingMode, trainingSessionId, nextInteractionMode) => {
          const chatPath = buildTrainingModeChatPath(
            roomId,
            nextTrainingMode,
            trainingSessionId,
            nextInteractionMode,
          )
          return `${chatPath}${chatPath.includes('?') ? '&' : '?'}${scenarioParam}`
        },
        buildNavigationState: ({ startedSession }) => ({
          ...buildScenarioTrainingRouteState(scenario),
          trainingMode,
          interactionMode,
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
          saveScenarioTrainingProgress(nextProgress, progressScope)
        },
      })
    } catch (error) {
      setDailyError(error instanceof Error ? error.message : tr('启动今日挑战失败', 'Failed to start today\'s challenge'))
    } finally {
      setDailyStarting(false)
    }
  }

  return (
    <PageShell className="home-page" width="wide">
      <PageHeader
        icon={<Target size={16} />}
        eyebrow={t('nav.home')}
        title={tr('训练入口', 'Training Index')}
        description={tr('选择训练、会话或复盘。', 'Open practice, conversations, or review.')}
        stats={(
          <PageStatGrid
            stats={[
              {
                label: tr('推荐训练', 'Recommended'),
                value: dailyStatusLabel,
                tone: 'success',
              },
              {
                label: tr('会话记录', 'Sessions'),
                value: rooms.length,
                detail: latestRoomTime,
                tone: 'warning',
              },
              {
                label: tr('使用身份', 'Identity'),
                value: operatorLabel,
                tone: 'accent',
              },
            ]}
          />
        )}
      />

      <div className="home-workbench-grid">
        <Surface className="home-primary-session" variant="accent" padding="lg">
          <div className="home-primary-session-head">
            <div>
              <Badge tone="success">{tr('推荐', 'Recommended')}</Badge>
              <h2>{tr(dailyChallenge.titleZh, dailyChallenge.titleEn)}</h2>
            </div>
            <Badge tone="warning">{dailyXpLabel}</Badge>
          </div>

          <div className="home-status-grid">
            <div className="home-status-card">
              <span>{tr('进度', 'Progress')}</span>
              <strong>{dailyProgressPercent}%</strong>
            </div>
            <div className="home-status-card">
              <span>{tr('模式', 'Mode')}</span>
              <strong>{tr('文本对话', 'Text chat')}</strong>
            </div>
            <div className="home-status-card">
              <span>{tr('范围', 'Scope')}</span>
              <strong>{operatorLabel}</strong>
            </div>
          </div>

          <div className="home-progress-block">
            <div className="home-progress-copy">
              <span>{tr('进度', 'Progress')}</span>
              <strong>{dailyProgressPercent}%</strong>
            </div>
            <div
              className="home-progress-track"
              role="progressbar"
              aria-label={tr('进度', 'Progress')}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={dailyProgressPercent}
            >
              <span style={{ width: `${dailyProgressPercent}%` }} />
            </div>
          </div>

          <div className="home-primary-actions">
            <Button
              className="home-primary-start"
              variant="primary"
              onClick={() => void startDailyChallenge()}
              disabled={dailyStarting}
            >
              {dailyStarting ? <Loader2 size={15} className="home-spin" /> : <Target size={15} />}
              {dailyStarting ? tr('启动中', 'Starting') : tr('开始训练', 'Start practice')}
            </Button>
            <Button asChild variant="secondary">
              <Link to={APP_ROUTES.practiceScenarios}>
                {tr('场景库', 'Scenario catalog')}
                <ChevronRight size={15} />
              </Link>
            </Button>
          </div>

          {dailyError && (
            <p className="home-inline-error" role="alert">{dailyError}</p>
          )}
        </Surface>

        <Surface className="home-task-panel" variant="raised" padding="lg">
          <div className="home-task-head">
            <Badge tone="neutral">{tr('继续', 'Continue')}</Badge>
            <h2>{tr('任务', 'Tasks')}</h2>
          </div>
          <div className="home-task-list">
            {latestRoom ? (
              <Link to={APP_ROUTES.conversation(latestRoom.id)} className="home-task-item">
                <span className="home-task-icon success">
                  <MessageSquare size={17} />
                </span>
                <div>
                  <strong>{tr('最近会话', 'Recent session')}</strong>
                  <em>{latestRoom.name}</em>
                </div>
                <ChevronRight size={15} />
              </Link>
            ) : (
              <div className="home-task-item is-disabled" aria-disabled="true">
                <span className="home-task-icon muted">
                  <MessageSquare size={17} />
                </span>
                <div>
                  <strong>{tr('最近会话', 'Recent session')}</strong>
                  <em>{tr('暂无可继续会话', 'No session yet')}</em>
                </div>
              </div>
            )}

            <Link to={APP_ROUTES.reviewSessions} className="home-task-item">
              <span className="home-task-icon warning">
                <History size={17} />
              </span>
              <div>
                <strong>{t('nav.review')}</strong>
                <em>{tr('训练复盘', 'Training reviews')}</em>
              </div>
              <ChevronRight size={15} />
            </Link>

            <Link to={APP_ROUTES.growth} className="home-task-item">
              <span className="home-task-icon accent">
                <TrendingUp size={17} />
              </span>
              <div>
                <strong>{t('nav.growth')}</strong>
                <em>{tr('能力进度', 'Skill progress')}</em>
              </div>
              <ChevronRight size={15} />
            </Link>
          </div>
        </Surface>
      </div>

      <PageSection
        title={tr('目录', 'Catalog')}
      >
        <div className="home-entry-grid">
          <Link to={APP_ROUTES.practiceScenarios} className="home-entry-card primary">
            <span className="home-entry-icon success">
              <ClipboardList size={19} />
            </span>
            <div>
              <Badge tone="success">{t('nav.practice')}</Badge>
              <strong>{t('nav.scenarioTraining')}</strong>
            </div>
            <ChevronRight size={16} />
          </Link>

          <Link to={APP_ROUTES.conversations} className="home-entry-card">
            <span className="home-entry-icon neutral">
              <MessageSquare size={19} />
            </span>
            <div>
              <Badge>{tr('模拟', 'Simulation')}</Badge>
              <strong>{t('nav.conversations')}</strong>
            </div>
            <ChevronRight size={16} />
          </Link>

          <Link to={APP_ROUTES.practiceDefense} className="home-entry-card">
            <span className="home-entry-icon accent">
              <FileText size={19} />
            </span>
            <div>
              <Badge tone="violet">{t('nav.practice')}</Badge>
              <strong>{tr('答辩准备', 'Defense prep')}</strong>
            </div>
            <ChevronRight size={16} />
          </Link>

          {canUseManagementActions && (
            <Link to={APP_ROUTES.practiceBattle} className="home-entry-card">
              <span className="home-entry-icon warning">
                <Swords size={19} />
              </span>
              <div>
                <Badge tone="warning">{tr('备战', 'Prep')}</Badge>
                <strong>{t('nav.battlePrep')}</strong>
              </div>
              <ChevronRight size={16} />
            </Link>
          )}
        </div>
      </PageSection>

      <div className="home-review-grid">
        <PageSection
          className="home-recent-section"
          title={tr('对话记录', 'Conversation log')}
          actions={(
            <Button asChild variant="ghost" size="sm">
              <Link to={APP_ROUTES.conversations}>
                {tr('全部会话', 'All sessions')}
                <ChevronRight size={14} />
              </Link>
            </Button>
          )}
        >
          <Surface className="home-recent-surface" padding="sm">
            {recentRooms.length === 0 ? (
              <div className="home-empty-block">
                <p>{tr('暂无对话记录', 'No conversation records')}</p>
                <Button asChild variant="secondary" size="sm">
                  <Link to={APP_ROUTES.practiceScenarios}>{tr('开始第一次训练', 'Start first practice')}</Link>
                </Button>
              </div>
            ) : (
              <div className="home-recent-list">
                {recentRooms.map((room) => {
                  const firstPersonaId = room.persona_ids?.[0]
                  const persona = firstPersonaId ? personaMap[firstPersonaId] : null
                  const initial = persona ? getInitial(persona.name) : getInitial(room.name)
                  const color = persona
                    ? (persona.avatar_color || getAvatarColor(firstPersonaId))
                    : getAvatarColor(room.id)
                  return (
                    <Link key={room.id} to={APP_ROUTES.conversation(room.id)} className="home-recent-item">
                      <span className="home-recent-avatar" style={{ backgroundColor: color }}>
                        {initial}
                      </span>
                      <span className="home-recent-copy">
                        <strong>{room.name}</strong>
                        <em>{timeAgo(room.last_message_at, tr) || tr('暂无时间', 'No time')}</em>
                      </span>
                      <ChevronRight size={15} />
                    </Link>
                  )
                })}
              </div>
            )}
          </Surface>
        </PageSection>

        <PageSection
          className="home-skill-section"
          title={tr('能力进度', 'Skill progress')}
          actions={(
            <Button asChild variant="ghost" size="sm">
              <Link to={APP_ROUTES.growth}>
                {t('nav.growth')}
                <ChevronRight size={14} />
              </Link>
            </Button>
          )}
        >
          <Surface className="home-skill-surface" padding="md">
            <div className="home-skill-chain">
              {skillNodes.map((node, idx) => (
                <React.Fragment key={node.labelZh}>
                  {idx > 0 && <span className="home-skill-line" />}
                  <div className={`home-skill-node home-skill-node--${node.status}`}>
                    <span className="home-skill-circle">
                      {node.status === 'done' && <Check size={14} />}
                      {node.status === 'locked' && <Lock size={12} />}
                      {node.status === 'current' && <span className="home-skill-dot" />}
                    </span>
                    <span className="home-skill-label">{tr(node.labelZh, node.labelEn)}</span>
                  </div>
                </React.Fragment>
              ))}
            </div>
          </Surface>
        </PageSection>
      </div>
    </PageShell>
  )
}

export default HomePage
