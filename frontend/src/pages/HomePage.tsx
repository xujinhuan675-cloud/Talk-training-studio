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
  Radio,
  Swords,
  Target,
  TrendingUp,
} from 'lucide-react'
import { useAppContext } from '../contexts/AppContext'
import { useAuthContext } from '../contexts/AuthContext'
import { fetchRooms, startBattle, type ChatRoom } from '../services/api'
import { MANAGEMENT_SYSTEM_ROLES } from '../services/auth'
import { createTrainingSession, startTrainingSession } from '../services/trainingSession'
import { buildTrainingModeChatPath } from '../services/trainingMode'
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
  const canUseManagementActions = hasAnySystemRole(MANAGEMENT_SYSTEM_ROLES)
  const dailyProgressPercent = Math.round(dailyChallenge.progress * 100)

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
      const progress = getScenarioTrainingProgress(progressScope)
      const trainingSession = await createTrainingSession({
        mode: trainingMode,
        scenario_template_id: scenario.id,
        user_id: progressScope.userId,
        team_id: progressScope.teamId,
        task_config: buildScenarioTrainingTaskConfig(scenario),
      })
      const room = await startBattle(buildScenarioTrainingBattlePayload(scenario, trainingMode))
      const startedSession = await startTrainingSession(trainingSession.session_id, {
        room_id: room.id,
      })
      const nextProgress = markScenarioTrainingStarted(
        progress,
        scenario.id,
        startedSession.session_id,
        progressScope,
      )
      saveScenarioTrainingProgress(nextProgress, progressScope)

      const roomId = startedSession.room_id || room.id
      const chatPath = buildTrainingModeChatPath(roomId, trainingMode, startedSession.session_id, interactionMode)
      const scenarioParam = `scenarioTrainingId=${encodeURIComponent(scenario.id)}`
      navigate(`${chatPath}${chatPath.includes('?') ? '&' : '?'}${scenarioParam}`, {
        state: {
          ...buildScenarioTrainingRouteState(scenario),
          trainingMode,
          interactionMode,
          trainingSessionId: startedSession.session_id,
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
        eyebrow={tr('沟通训练工作台', 'Communication training workspace')}
        title={tr('从目标进入训练，再把复盘变成下一次练习', 'Start with a goal, practice, then turn review into the next drill')}
        description={tr(
          '主线围绕场景训练、AI 对话、实时提示、训练复盘和成长路径组织。自由聊天和专项准备保留为辅助入口。',
          'The main loop is organized around scenario practice, AI conversation, live guidance, review, and growth. Free chat and special prep remain secondary entry points.',
        )}
        actions={(
          <>
            <Button asChild variant="primary">
              <Link to="/scenario-training">
                <ClipboardList size={15} />
                {tr('选择训练场景', 'Choose scenario')}
              </Link>
            </Button>
            <Button asChild variant="ghost">
              <Link to="/training-history">
                <History size={15} />
                {tr('查看复盘', 'Review history')}
              </Link>
            </Button>
          </>
        )}
        stats={(
          <PageStatGrid
            stats={[
              {
                label: tr('主线入口', 'Primary path'),
                value: t('nav.scenarioTraining'),
                detail: tr('目标 -> 对话 -> 复盘', 'Goal -> chat -> review'),
                tone: 'success',
              },
              {
                label: tr('今日推荐', 'Today'),
                value: `+${dailyChallenge.xp} XP`,
                detail: tr(dailyChallenge.titleZh, dailyChallenge.titleEn),
                tone: 'warning',
              },
              {
                label: tr('最近房间', 'Recent rooms'),
                value: rooms.length,
                detail: currentUser?.teamName ?? currentUser?.name ?? tr('模拟用户', 'Mock user'),
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
              <Badge tone="success">{tr('推荐训练', 'Recommended drill')}</Badge>
              <h2>{tr(dailyChallenge.titleZh, dailyChallenge.titleEn)}</h2>
            </div>
            <Badge tone="warning">+{dailyChallenge.xp} XP</Badge>
          </div>

          <div className="home-mode-strip" aria-label={tr('支持的训练方式', 'Supported practice modes')}>
            <span>
              <MessageSquare size={14} />
              {tr('文本', 'Text')}
            </span>
            <span>
              <Radio size={14} />
              {tr('语音/实时', 'Voice/realtime')}
            </span>
            <span>
              <TrendingUp size={14} />
              {tr('复盘成长', 'Review growth')}
            </span>
          </div>

          <div className="home-progress-block">
            <div className="home-progress-copy">
              <span>{tr('建议进度', 'Suggested progress')}</span>
              <strong>{dailyProgressPercent}%</strong>
            </div>
            <div className="home-progress-track">
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
              {dailyStarting ? tr('启动中', 'Starting') : tr('开始推荐训练', 'Start recommended drill')}
            </Button>
            <Button asChild variant="secondary">
              <Link to="/scenario-training">
                {tr('浏览全部场景', 'Browse scenarios')}
                <ChevronRight size={15} />
              </Link>
            </Button>
          </div>

          {dailyError && (
            <p className="home-inline-error" role="alert">{dailyError}</p>
          )}
        </Surface>

        <Surface className="home-loop-panel" variant="raised" padding="lg">
          <div className="home-loop-head">
            <Badge tone="neutral">{tr('训练闭环', 'Training loop')}</Badge>
            <h2>{tr('本次练习应如何完成', 'How this practice should complete')}</h2>
          </div>
          <ol className="home-loop-list">
            <li className="active">
              <span>1</span>
              <div>
                <strong>{tr('选择目标和场景', 'Choose goal and scenario')}</strong>
              </div>
            </li>
            <li>
              <span>2</span>
              <div>
                <strong>{tr('进入多模态对话', 'Enter multimodal conversation')}</strong>
              </div>
            </li>
            <li>
              <span>3</span>
              <div>
                <strong>{tr('复盘并继续训练', 'Review and continue')}</strong>
              </div>
            </li>
          </ol>
        </Surface>
      </div>

      <PageSection
        title={tr('训练入口', 'Training entry points')}
      >
        <div className="home-entry-grid" aria-label={tr('训练入口', 'Training entry points')}>
          <Link to="/scenario-training" className="home-entry-card primary">
            <span className="home-entry-icon success">
              <ClipboardList size={19} />
            </span>
            <div>
              <Badge tone="success">{t('nav.scenarioTraining')}</Badge>
              <strong>{tr('按业务场景开练', 'Practice by business scenario')}</strong>
            </div>
            <ChevronRight size={16} />
          </Link>

          <Link to="/chat" className="home-entry-card">
            <span className="home-entry-icon neutral">
              <MessageSquare size={19} />
            </span>
            <div>
              <Badge>{tr('辅助入口', 'Secondary')}</Badge>
              <strong>{tr('开放式沟通模拟', 'Open communication simulation')}</strong>
            </div>
            <ChevronRight size={16} />
          </Link>

          <Link to="/defense-prep" className="home-entry-card">
            <span className="home-entry-icon accent">
              <FileText size={19} />
            </span>
            <div>
              <Badge tone="violet">{tr('专项准备', 'Special prep')}</Badge>
              <strong>{tr('模拟答辩演练', 'Mock defense practice')}</strong>
            </div>
            <ChevronRight size={16} />
          </Link>

          {canUseManagementActions && (
            <Link to="/battle-prep" className="home-entry-card">
            <span className="home-entry-icon warning">
              <Swords size={19} />
            </span>
            <div>
              <Badge tone="warning">{t('nav.battlePrep')}</Badge>
              <strong>{tr('30 分钟快速演练', '30-minute fast drill')}</strong>
            </div>
            <ChevronRight size={16} />
          </Link>
          )}
        </div>
      </PageSection>

      <div className="home-review-grid">
        <PageSection
          className="home-recent-section"
          title={tr('最近对话', 'Recent conversations')}
          actions={(
            <Button asChild variant="ghost" size="sm">
              <Link to="/chat">
                {tr('查看全部', 'View all')}
                <ChevronRight size={14} />
              </Link>
            </Button>
          )}
        >
          <Surface className="home-recent-surface" padding="sm">
            {recentRooms.length === 0 ? (
              <div className="home-empty-block">
                <p>{tr('还没有对话记录', 'No conversations yet')}</p>
                <Button asChild variant="secondary" size="sm">
                  <Link to="/scenario-training">{tr('开始第一次训练', 'Start first practice')}</Link>
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
                    <Link key={room.id} to={`/chat/${room.id}`} className="home-recent-item">
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
          title={tr('能力路径', 'Skill path')}
          actions={(
            <Button asChild variant="ghost" size="sm">
              <Link to="/growth">
                {tr('展开', 'Expand')}
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
