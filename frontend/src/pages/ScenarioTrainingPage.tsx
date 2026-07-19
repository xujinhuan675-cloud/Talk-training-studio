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
  ShieldCheck,
  SlidersHorizontal,
  Trophy,
} from 'lucide-react'
import { startBattle } from '../services/api'
import { fetchScenarioTrainingCatalog, fetchScenarioTrainingProgress } from '../services/scenarioTraining'
import { buildTrainingSessionStartRequest, createTrainingSession, startTrainingSession } from '../services/trainingSession'
import {
  buildTrainingModeChatPath,
  type InteractionMode,
  type TrainingMode,
} from '../services/trainingMode'
import { launchTrainingSessionFlow } from '../services/trainingLaunch'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n, type Locale, type Translate, type TranslateInline } from '../i18n'
import { MANAGEMENT_SYSTEM_ROLES } from '../services/auth'
import { PageHeader, PageShell } from '../components/ui/page'
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
  type ScenarioTrainingProgress,
} from '../data/trainingScenarios'
import {
  getScenarioCategoryFilterLabel,
  getScenarioCategoryLabel,
  getScenarioDifficultyFilterLabel,
  getScenarioDifficultyLabel,
  getScenarioStatusLabel,
  scenarioCategoryOptions,
  scenarioDifficultyOptions,
  type ScenarioCategoryFilter,
  type ScenarioDifficultyFilter,
} from '../utils/scenarioLabels'
import { APP_ROUTES } from '../appRoutes'
import { Button } from '../components/ui/button'
import './ScenarioTrainingPage.css'

type DifficultyFilter = ScenarioDifficultyFilter
type CategoryFilter = ScenarioCategoryFilter
type ScenarioLaunchMode = TrainingMode | 'realtime'

const difficultyOptions: DifficultyFilter[] = ['all', ...scenarioDifficultyOptions]
const categoryOptions: CategoryFilter[] = ['all', ...scenarioCategoryOptions]
const modeOptions: ScenarioLaunchMode[] = ['text', 'voice', 'realtime']

function getModeLabel(value: ScenarioLaunchMode, t: Translate): string {
  switch (value) {
    case 'text':
      return t('training.mode.text.label')
    case 'voice':
      return t('training.mode.voice.label')
    case 'video':
      return t('training.mode.video.label')
    case 'realtime':
      return t('training.mode.realtime.label')
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
  const { locale, t, tr } = useI18n()
  const { currentUser, hasAnySystemRole } = useAuthContext()
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
  const canUseManagementActions = hasAnySystemRole(MANAGEMENT_SYSTEM_ROLES)

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

  const startScenario = async (scenario: ScenarioTrainingCard) => {
    setStartingScenarioId(scenario.id)
    setError(null)
    try {
      const trainingMode = getScenarioTrainingMode(mode)
      const interactionMode = getScenarioInteractionMode(mode)
      const useConversationMessageTreeRuntime = trainingMode === 'text' && interactionMode === 'turn_based'
      const scenarioParam = `scenarioTrainingId=${encodeURIComponent(scenario.id)}`
      const taskConfig = buildScenarioTrainingTaskConfig(scenario)
      const scenarioTrainingMetadata = taskConfig.metadata?.scenario_training
      const scenarioTrainingRecord = scenarioTrainingMetadata
        && typeof scenarioTrainingMetadata === 'object'
        && !Array.isArray(scenarioTrainingMetadata)
        ? scenarioTrainingMetadata as Record<string, unknown>
        : {}
      await launchTrainingSessionFlow({
        createTrainingSessionRequest: {
          mode: trainingMode,
          scenario_template_id: scenario.id,
          user_id: progressScope.userId,
          team_id: progressScope.teamId,
          task_config: {
            ...taskConfig,
            metadata: {
              ...taskConfig.metadata,
              trainingMode,
              interactionMode,
              trainingProfile: 'practice',
              scenario_training: {
                ...scenarioTrainingRecord,
                trainingMode,
                interactionMode,
              },
            },
          },
        },
        createTrainingSession,
        battlePayload: useConversationMessageTreeRuntime
          ? null
          : buildScenarioTrainingBattlePayload(scenario, trainingMode),
        startBattle,
        startTrainingSession,
        buildTrainingSessionStartRequest,
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
          setProgress(nextProgress)
          saveScenarioTrainingProgress(nextProgress, progressScope)
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
        title={tr('训练目录', 'Training catalog')}
        description={tr('筛选场景，选择模式，然后进入训练。', 'Filter scenarios, choose a mode, and start training.')}
        actions={canUseManagementActions ? (
          <Button asChild variant="secondary" size="sm">
            <Link to={APP_ROUTES.practiceCustom}>
              <SlidersHorizontal size={14} />
              {t('nav.trainingStudio')}
            </Link>
          </Button>
        ) : null}
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
                {getScenarioDifficultyFilterLabel(option, tr)}
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
                {getScenarioCategoryFilterLabel(option, tr)}
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
              {getModeLabel(option, t)}
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
                      {getScenarioDifficultyLabel(scenario.difficulty, tr)}
                    </span>
                    <span>{getScenarioCategoryLabel(scenario.category, tr)}</span>
                    {scenario.required && <span className="required">{tr('必练', 'Required')}</span>}
                  </div>
                  <h2>{scenario.title}</h2>
                  <p className="scenario-training-card-description">{scenario.description}</p>
                </div>
                <span className={`scenario-training-status ${scenario.status}`}>
                  {scenario.status === 'completed' && <CheckCircle2 size={14} />}
                  {scenario.status === 'in_progress' && <Clock3 size={14} />}
                  {scenario.status === 'not_started' && <ShieldCheck size={14} />}
                  {scenario.status === 'failed' && <AlertCircle size={14} />}
                  {getScenarioStatusLabel(scenario.status, tr)}
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

              {scenario.trainingPoints.length > 0 && (
                <div className="scenario-training-points" aria-label={tr('训练要点', 'Training points')}>
                  {scenario.trainingPoints.slice(0, 2).map((point) => (
                    <span key={point}>{point}</span>
                  ))}
                </div>
              )}

              <div className="scenario-training-actions">
                <button
                  type="button"
                  className="scenario-training-start"
                  onClick={() => void startScenario(scenario)}
                  disabled={startingScenarioId !== null}
                >
                  {starting ? <Loader2 size={16} className="scenario-training-spin" /> : <Play size={16} />}
                  {starting ? t('common.starting') : t('common.startPractice')}
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
