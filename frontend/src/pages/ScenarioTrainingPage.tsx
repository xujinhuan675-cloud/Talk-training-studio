import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Loader2,
  Play,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Trophy,
} from 'lucide-react'
import { startBattle } from '../services/api'
import { fetchScenarioTrainingCatalog, fetchScenarioTrainingProgress } from '../services/scenarioTraining'
import { createTrainingSession, startTrainingSession } from '../services/trainingSession'
import {
  buildTrainingModeChatPath,
  type InteractionMode,
  type TrainingMode,
} from '../services/trainingMode'
import { buildTrainingSessionStartRequest } from '../services/trainingSession'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n, type Locale, type TranslateInline } from '../i18n'
import { PageHeader, PageShell, PageStatGrid } from '../components/ui/page'
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

const difficultyOptions: DifficultyFilter[] = ['all', 'easy', 'medium', 'hard', 'expert']
const categoryOptions: CategoryFilter[] = ['all', 'sales', 'customer_service', 'negotiation', 'interview', 'workplace']
const modeOptions: ScenarioLaunchMode[] = ['text', 'voice', 'realtime']

function getDifficultyLabel(value: ScenarioTrainingDifficulty, tr: TranslateInline): string {
  switch (value) {
    case 'easy':
      return tr('轻量', 'Light')
    case 'medium':
      return tr('标准', 'Standard')
    case 'hard':
      return tr('高压', 'High pressure')
    case 'expert':
      return tr('专家', 'Expert')
  }
}

function getDifficultyFilterLabel(value: DifficultyFilter, tr: TranslateInline): string {
  return value === 'all' ? tr('全部难度', 'All difficulties') : getDifficultyLabel(value, tr)
}

function getCategoryLabel(value: ScenarioTrainingCategory, tr: TranslateInline): string {
  switch (value) {
    case 'sales':
      return tr('销售', 'Sales')
    case 'customer_service':
      return tr('客服', 'Service')
    case 'negotiation':
      return tr('谈判', 'Negotiation')
    case 'interview':
      return tr('面试', 'Interview')
    case 'workplace':
      return tr('职场沟通', 'Workplace')
  }
}

function getCategoryFilterLabel(value: CategoryFilter, tr: TranslateInline): string {
  return value === 'all' ? tr('全部类型', 'All categories') : getCategoryLabel(value, tr)
}

function getModeLabel(value: ScenarioLaunchMode, tr: TranslateInline): string {
  switch (value) {
    case 'text':
      return tr('文本', 'Text')
    case 'voice':
      return tr('语音', 'Voice')
    case 'video':
      return tr('视频', 'Video')
    case 'realtime':
      return tr('实时', 'Realtime')
  }
}

function getStatusLabel(status: ScenarioTrainingStatus, tr: TranslateInline): string {
  switch (status) {
    case 'not_started':
      return tr('未开始', 'Not started')
    case 'in_progress':
      return tr('练习中', 'In progress')
    case 'completed':
      return tr('已完成', 'Completed')
    case 'failed':
      return tr('失败', 'Failed')
  }
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function getScenarioTrainingMode(mode: ScenarioLaunchMode): TrainingMode {
  return mode === 'realtime' ? 'voice' : mode
}

function getScenarioInteractionMode(mode: ScenarioLaunchMode): InteractionMode {
  return mode === 'realtime' ? 'realtime' : 'turn_based'
}

function formatDate(value: string | undefined, locale: Locale, tr: TranslateInline): string {
  if (!value) return tr('未练习', 'Not practiced')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US', {
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
  const { locale, tr } = useI18n()
  const { currentUser } = useAuthContext()
  const [mode, setMode] = useState<ScenarioLaunchMode>('text')
  const [query, setQuery] = useState('')
  const [difficulty, setDifficulty] = useState<DifficultyFilter>('all')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [catalog, setCatalog] = useState<ScenarioTrainingCard[]>(scenarioTrainingCatalog)
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
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return
        void e
        setCatalog(scenarioTrainingCatalog)
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
      .catch((e: unknown) => {
        void e
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
      const startedSession = await startTrainingSession(
        trainingSession.session_id,
        buildTrainingSessionStartRequest(
          { room_id: room.id },
          trainingMode,
          interactionMode,
        ),
      )
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
      setError(getErrorMessage(e, tr('启动训练失败', 'Failed to start training')))
      setStartingScenarioId(null)
    }
  }

  return (
    <PageShell width="wide" className="scenario-training-page">
      <PageHeader
        title={tr('场景训练', 'Scenario training')}
        stats={(
          <PageStatGrid
            stats={[
              {
                label: tr('必练完成', 'Required done'),
                value: `${completedRequired}/${requiredTotal}`,
              },
              {
                label: tr('平均分', 'Average score'),
                value: scoreText,
              },
              {
                label: tr('匹配场景', 'Matched scenarios'),
                value: filteredScenarios.length,
              },
            ]}
          />
        )}
      />

      <section className="scenario-training-toolbar" aria-label={tr('筛选与模式', 'Filters and mode')}>
        <label className="scenario-training-search">
          <Search size={16} />
          <input
            aria-label={tr('搜索场景', 'Search scenarios')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tr('搜索客户、异议、场景...', 'Search customers, objections, scenarios...')}
          />
        </label>

        <label className="scenario-training-select">
          <SlidersHorizontal size={15} />
          <select
            aria-label={tr('难度筛选', 'Difficulty filter')}
            value={difficulty}
            onChange={(event) => setDifficulty(event.target.value as DifficultyFilter)}
          >
            {difficultyOptions.map((option) => (
              <option key={option} value={option}>
                {getDifficultyFilterLabel(option, tr)}
              </option>
            ))}
          </select>
        </label>

        <label className="scenario-training-select">
          <ClipboardList size={15} />
          <select
            aria-label={tr('类型筛选', 'Category filter')}
            value={category}
            onChange={(event) => setCategory(event.target.value as CategoryFilter)}
          >
            {categoryOptions.map((option) => (
              <option key={option} value={option}>
                {getCategoryFilterLabel(option, tr)}
              </option>
            ))}
          </select>
        </label>

        <div className="scenario-training-mode" role="group" aria-label={tr('训练模式', 'Training mode')}>
          <span className="scenario-training-mode-label">{tr('模式', 'Mode')}</span>
          {modeOptions.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={mode === option}
              className={mode === option ? 'selected' : ''}
              onClick={() => setMode(option)}
            >
              {getModeLabel(option, tr)}
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
                      {getDifficultyLabel(scenario.difficulty, tr)}
                    </span>
                    <span>{getCategoryLabel(scenario.category, tr)}</span>
                    {scenario.required && <span className="required">{tr('必练', 'Required')}</span>}
                  </div>
                  <h2>{scenario.title}</h2>
                </div>
                <span className={`scenario-training-status ${scenario.status}`}>
                  {scenario.status === 'completed' && <CheckCircle2 size={14} />}
                  {scenario.status === 'in_progress' && <Clock3 size={14} />}
                  {scenario.status === 'not_started' && <ShieldCheck size={14} />}
                  {scenario.status === 'failed' && <AlertCircle size={14} />}
                  {getStatusLabel(scenario.status, tr)}
                </span>
              </div>

              <div className="scenario-training-card-status">
                <span aria-label={tr('分数', 'Score')}>
                  <Trophy size={14} />
                  {typeof scenario.score === 'number'
                    ? tr('{score} 分', '{score} pts', { score: scenario.score })
                    : scenario.scoreStatus === 'pending' && scenario.status === 'completed'
                      ? tr('评分中', 'Scoring')
                      : tr('暂无分数', 'No score')}
                </span>
                <span aria-label={tr('最近练习', 'Last practiced')}>
                  <Clock3 size={14} />
                  {formatDate(scenario.lastPracticedAt, locale, tr)}
                </span>
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
    </PageShell>
  )
}
