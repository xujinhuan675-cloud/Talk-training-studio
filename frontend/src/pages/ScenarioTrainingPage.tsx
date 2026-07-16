import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Loader2,
  Play,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Trophy,
  UserRound,
} from 'lucide-react'
import { startBattle } from '../services/api'
import { fetchScenarioTrainingCatalog, fetchScenarioTrainingProgress } from '../services/scenarioTraining'
import { createTrainingSession, startTrainingSession } from '../services/trainingSession'
import {
  buildTrainingModeChatPath,
  type InteractionMode,
  type TrainingMode,
} from '../services/trainingMode'
import { useAuthContext } from '../contexts/AuthContext'
import { getUserDisplayRoleName } from '../services/auth'
import { useI18n } from '../i18n'
import {
  buildScenarioTrainingBattlePayload,
  buildScenarioTrainingRouteState,
  buildScenarioTrainingTaskConfig,
  getScenarioTrainingProgress,
  markScenarioTrainingStarted,
  mergeScenarioTrainingProgress,
  mergeScenarioTrainingProgressRecords,
  saveScenarioTrainingProgress,
  scenarioTrainingCatalog,
  type ScenarioTrainingCard,
  type ScenarioTrainingCategory,
  type ScenarioTrainingDifficulty,
  type ScenarioTrainingProgress,
  type ScenarioTrainingStatus,
} from '../data/trainingScenarios'
import './ScenarioTrainingPage.css'

type DifficultyFilter = 'all' | ScenarioTrainingDifficulty
type CategoryFilter = 'all' | ScenarioTrainingCategory
type ScenarioLaunchMode = TrainingMode | 'realtime'

const difficultyOptions: Array<{ value: DifficultyFilter; label: string }> = [
  { value: 'all', label: '全部难度' },
  { value: 'easy', label: '轻量' },
  { value: 'medium', label: '标准' },
  { value: 'hard', label: '高压' },
  { value: 'expert', label: '专家' },
]

const categoryOptions: Array<{ value: CategoryFilter; label: string }> = [
  { value: 'all', label: '全部类型' },
  { value: 'sales', label: '销售' },
  { value: 'customer_service', label: '客服' },
  { value: 'negotiation', label: '谈判' },
  { value: 'interview', label: '面试' },
]

const modeOptions: Array<{ value: ScenarioLaunchMode; label: string }> = [
  { value: 'text', label: '文本' },
  { value: 'voice', label: '语音' },
  { value: 'realtime', label: '实时' },
]

const difficultyLabels: Record<ScenarioTrainingDifficulty, string> = {
  easy: '轻量',
  medium: '标准',
  hard: '高压',
  expert: '专家',
}

const categoryLabels: Record<ScenarioTrainingCategory, string> = {
  sales: '销售',
  customer_service: '客服',
  negotiation: '谈判',
  interview: '面试',
}

const statusLabels: Record<ScenarioTrainingStatus, string> = {
  not_started: '未开始',
  in_progress: '练习中',
  completed: '已完成',
  failed: '失败',
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '启动训练失败'
}

function getScenarioTrainingMode(mode: ScenarioLaunchMode): TrainingMode {
  return mode === 'realtime' ? 'voice' : mode
}

function getScenarioInteractionMode(mode: ScenarioLaunchMode): InteractionMode {
  return mode === 'realtime' ? 'realtime' : 'turn_based'
}

function formatDate(value?: string): string {
  if (!value) return '未练习'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
  })
}

function matchesScenario(
  scenario: ScenarioTrainingCard,
  query: string,
  difficulty: DifficultyFilter,
  category: CategoryFilter,
): boolean {
  if (difficulty !== 'all' && scenario.difficulty !== difficulty) return false
  if (category !== 'all' && scenario.category !== category) return false
  if (!query.trim()) return true

  const needle = query.trim().toLowerCase()
  return [
    scenario.title,
    scenario.description,
    scenario.customerProfile,
    scenario.persona.name,
    scenario.persona.role,
    ...scenario.trainingPoints,
  ].some((value) => value.toLowerCase().includes(needle))
}

export default function ScenarioTrainingPage() {
  const navigate = useNavigate()
  const { tr } = useI18n()
  const { currentUser, isAdmin } = useAuthContext()
  const [mode, setMode] = useState<ScenarioLaunchMode>('text')
  const [query, setQuery] = useState('')
  const [difficulty, setDifficulty] = useState<DifficultyFilter>('all')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [catalog, setCatalog] = useState<ScenarioTrainingCard[]>(scenarioTrainingCatalog)
  const [catalogSource, setCatalogSource] = useState<'api' | 'fallback'>('fallback')
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [progressError, setProgressError] = useState<string | null>(null)
  const progressScope = useMemo(() => ({
    userId: currentUser?.userId ?? null,
    teamId: currentUser?.teamId ?? null,
  }), [currentUser?.teamId, currentUser?.userId])
  const [progress, setProgress] = useState<ScenarioTrainingProgress>(() => (
    getScenarioTrainingProgress(progressScope)
  ))
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setProgress(getScenarioTrainingProgress(progressScope))
  }, [progressScope])

  useEffect(() => {
    let cancelled = false

    fetchScenarioTrainingCatalog()
      .then((templates) => {
        if (cancelled) return
        if (templates.length > 0) {
          setCatalog(templates)
          setCatalogSource('api')
        }
        setCatalogError(null)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setCatalog(scenarioTrainingCatalog)
        setCatalogSource('fallback')
        setCatalogError(getErrorMessage(e))
      })
      .finally(() => {
        if (!cancelled) {
          setCatalogLoading(false)
        }
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
        setProgressError(null)
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setProgressError(getErrorMessage(e))
        }
      })

    return () => {
      cancelled = true
    }
  }, [progressScope])

  const scenarios = useMemo(
    () => mergeScenarioTrainingProgress(catalog, progress),
    [catalog, progress],
  )

  const filteredScenarios = useMemo(
    () => scenarios.filter((scenario) => matchesScenario(scenario, query, difficulty, category)),
    [category, difficulty, query, scenarios],
  )

  const requiredTotal = scenarios.filter((scenario) => scenario.required).length
  const completedRequired = scenarios.filter(
    (scenario) => scenario.required && scenario.status === 'completed',
  ).length
  const averageScore = scenarios
    .map((scenario) => scenario.score)
    .filter((score): score is number => typeof score === 'number')
  const scoreText = averageScore.length
    ? Math.round(averageScore.reduce((sum, score) => sum + score, 0) / averageScore.length)
    : '--'
  const catalogSourceText = catalogLoading
    ? tr('正在加载后端场景模板...', 'Loading backend scenario templates...')
    : catalogSource === 'api'
      ? tr('当前目录来自后端场景模板 API。', 'Catalog source: backend scenario template API.')
      : tr('后端模板暂不可用，当前使用本地 MVP 场景目录。', 'Backend templates unavailable; using the local MVP catalog.')

  const startScenario = async (scenario: ScenarioTrainingCard) => {
    setStartingScenarioId(scenario.id)
    setError(null)
    try {
      const trainingMode = getScenarioTrainingMode(mode)
      const interactionMode = getScenarioInteractionMode(mode)
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
      setProgress(nextProgress)
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
    } catch (e: unknown) {
      setError(getErrorMessage(e))
      setStartingScenarioId(null)
    }
  }

  return (
    <div className="scenario-training-page">
      <section className="scenario-training-hero">
        <div className="scenario-training-title-block">
          <div className="scenario-training-kicker">
            <ClipboardList size={16} />
            <span>{tr('按场景训练', 'Scenario training')}</span>
          </div>
          <h1>{tr('真实销售与客服场景练习', 'Real-world sales and service drills')}</h1>
          <p>
            {tr(
              '从业务场景卡片直接进入 AI 客户陪练，训练记录会复用现有 Training Session、ChatPage、报告和实时指导链路。',
              'Start from business scenario cards and reuse the existing Training Session, ChatPage, report, and guidance flow.',
            )}
          </p>
        </div>

        <div className="scenario-training-summary" aria-label={tr('训练概览', 'Training overview')}>
          <div>
            <span>{completedRequired}/{requiredTotal}</span>
            <small>{tr('必练完成', 'Required done')}</small>
          </div>
          <div>
            <span>{scoreText}</span>
            <small>{tr('平均分', 'Average score')}</small>
          </div>
          <div>
            <span>{currentUser ? getUserDisplayRoleName(currentUser) : tr('未登录', 'Signed out')}</span>
            <small>{currentUser?.teamName ?? currentUser?.name ?? tr('模拟用户', 'Mock user')}</small>
          </div>
        </div>
      </section>

      <section className="scenario-training-toolbar" aria-label={tr('场景筛选', 'Scenario filters')}>
        <label className="scenario-training-search">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tr('搜索客户、异议、场景...', 'Search customers, objections, scenarios...')}
          />
        </label>

        <label className="scenario-training-select">
          <SlidersHorizontal size={15} />
          <select
            value={difficulty}
            onChange={(event) => setDifficulty(event.target.value as DifficultyFilter)}
          >
            {difficultyOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="scenario-training-select">
          <ClipboardList size={15} />
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as CategoryFilter)}
          >
            {categoryOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <div className="scenario-training-mode" role="group" aria-label={tr('训练模式', 'Training mode')}>
          {modeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              className={mode === option.value ? 'selected' : ''}
              onClick={() => setMode(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>

      {error && (
        <div className="scenario-training-error" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <section className="scenario-training-grid" aria-label={tr('场景卡片', 'Scenario cards')}>
        {filteredScenarios.map((scenario) => {
          const starting = startingScenarioId === scenario.id
          return (
            <article className="scenario-training-card" key={scenario.id}>
              <div className="scenario-training-card-head">
                <div>
                  <div className="scenario-training-card-tags">
                    <span className={`difficulty ${scenario.difficulty}`}>
                      {difficultyLabels[scenario.difficulty]}
                    </span>
                    <span>{categoryLabels[scenario.category]}</span>
                    {scenario.required && <span className="required">{tr('必练', 'Required')}</span>}
                  </div>
                  <h2>{scenario.title}</h2>
                </div>
                <span className={`scenario-training-status ${scenario.status}`}>
                  {scenario.status === 'completed' && <CheckCircle2 size={14} />}
                  {scenario.status === 'in_progress' && <Clock3 size={14} />}
                  {scenario.status === 'not_started' && <ShieldCheck size={14} />}
                  {statusLabels[scenario.status]}
                </span>
              </div>

              <p className="scenario-training-desc">{scenario.description}</p>

              <div className="scenario-training-customer">
                <UserRound size={16} />
                <span>{scenario.customerProfile}</span>
              </div>

              <blockquote>{scenario.openingLine}</blockquote>

              <div className="scenario-training-meta">
                <span>
                  <Trophy size={14} />
                  {typeof scenario.score === 'number'
                    ? `${scenario.score} 分`
                    : scenario.scoreStatus === 'pending' && scenario.status === 'completed'
                      ? tr('评分中', 'Scoring')
                      : tr('暂无分数', 'No score')}
                </span>
                <span>
                  <Clock3 size={14} />
                  {formatDate(scenario.lastPracticedAt)}
                </span>
              </div>

              <div className="scenario-training-points">
                {scenario.trainingPoints.map((point) => (
                  <span key={point}>{point}</span>
                ))}
              </div>

              <div className="scenario-training-actions">
                <button
                  type="button"
                  className="scenario-training-start"
                  onClick={() => void startScenario(scenario)}
                  disabled={startingScenarioId !== null}
                >
                  {starting ? <Loader2 size={16} className="scenario-training-spin" /> : <Play size={16} />}
                  {starting ? tr('启动中', 'Starting') : tr('开始练习', 'Start practice')}
                </button>
              </div>
            </article>
          )
        })}
      </section>

      {filteredScenarios.length === 0 && (
        <section className="scenario-training-empty">
          <Search size={24} />
          <p>{tr('没有匹配的训练场景', 'No matching scenarios')}</p>
        </section>
      )}

      {isAdmin && (
        <section className="scenario-training-admin">
          <div>
            <strong>{tr('管理员入口', 'Admin entry')}</strong>
            <span>
              {catalogSourceText}
              {catalogError ? ` ${catalogError}` : ''}
              {progressError ? ` ${tr('进度同步失败：', 'Progress sync failed: ')}${progressError}` : ''}
            </span>
          </div>
          <Link to="/training-studio">
            <Settings size={16} />
            {tr('训练配置', 'Training config')}
          </Link>
        </section>
      )}
    </div>
  )
}
