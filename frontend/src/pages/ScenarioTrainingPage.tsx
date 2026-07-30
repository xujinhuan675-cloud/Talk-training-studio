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
import { fetchScenarioTrainingCatalog, fetchScenarioTrainingProgress } from '../services/scenarioTraining'
import { type TrainingFeedbackMode, type TrainingMode } from '../services/trainingMode'
import { launchScenarioTraining } from '../services/scenarioTrainingLaunch'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n, type Locale, type Translate, type TranslateInline } from '../i18n'
import { PageHeader, PageShell } from '../components/ui/page'
import {
  getScenarioTrainingProgress,
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
import { Input, Select } from '../components/ui/form'
import { SegmentedControl } from '../components/ui/segmented-control'
import './ScenarioTrainingPage.css'

type DifficultyFilter = ScenarioDifficultyFilter
type CategoryFilter = ScenarioCategoryFilter

const difficultyOptions: DifficultyFilter[] = ['all', ...scenarioDifficultyOptions]
const categoryOptions: CategoryFilter[] = ['all', ...scenarioCategoryOptions]
const modeOptions: TrainingMode[] = ['text', 'voice', 'video']
const feedbackModeOptions: TrainingFeedbackMode[] = ['simulation', 'assisted', 'drill']

function getModeLabel(value: TrainingMode, t: Translate): string {
  switch (value) {
    case 'text':
      return t('training.mode.text.label')
    case 'voice':
      return t('training.mode.voice.label')
    case 'video':
      return t('training.mode.video.label')
  }
}

function getFeedbackModeLabel(value: TrainingFeedbackMode, tr: TranslateInline): string {
  switch (value) {
    case 'simulation':
      return tr('完整模拟', 'Simulation')
    case 'assisted':
      return tr('旁路提示', 'Assisted')
    case 'drill':
      return tr('逐句纠正', 'Drill')
  }
}

function getFeedbackModeDescription(value: TrainingFeedbackMode, tr: TranslateInline): string {
  switch (value) {
    case 'simulation':
      return tr('连续对话，结束后统一复盘。', 'Continuous interview, review at the end.')
    case 'assisted':
      return tr('不中断对话，旁边给下一句和风险提示。', 'Side guidance without interrupting the conversation.')
    case 'drill':
      return tr('说一句、改一句，达标后再进入下一题。', 'Correct each answer before moving on.')
  }
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
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
  const { currentUser, isAdmin, requireAuthenticated } = useAuthContext()
  const [mode, setMode] = useState<TrainingMode>('text')
  const [feedbackMode, setFeedbackMode] = useState<TrainingFeedbackMode>('simulation')
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
  const canUseManagementActions = isAdmin

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
    if (!requireAuthenticated()) return
    setStartingScenarioId(scenario.id)
    setError(null)
    try {
      await launchScenarioTraining({
        scenario,
        mode,
        feedbackMode,
        progress,
        progressScope,
        navigate,
        onProgressChange: setProgress,
      })
    } catch (e: unknown) {
      setError(getErrorMessage(e, tr('启动训练失败', 'Failed to start training')))
      setStartingScenarioId(null)
    }
  }

  return (
    <PageShell className="scenario-training-page">
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
          <Input
            aria-label={tr('搜索场景', 'Search scenarios')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tr('搜索客户、异议、场景...', 'Search customers, objections, scenarios...')}
          />
        </label>

        <label className="scenario-training-select">
          <SlidersHorizontal size={15} />
          <Select
            aria-label={tr('难度筛选', 'Difficulty filter')}
            value={difficulty}
            onChange={(event) => setDifficulty(event.target.value as DifficultyFilter)}
          >
            {difficultyOptions.map((option) => (
              <option key={option} value={option}>
                {getScenarioDifficultyFilterLabel(option, tr)}
              </option>
            ))}
          </Select>
        </label>

        <label className="scenario-training-select">
          <ClipboardList size={15} />
          <Select
            aria-label={tr('类型筛选', 'Category filter')}
            value={category}
            onChange={(event) => setCategory(event.target.value as CategoryFilter)}
          >
            {categoryOptions.map((option) => (
              <option key={option} value={option}>
                {getScenarioCategoryFilterLabel(option, tr)}
              </option>
            ))}
          </Select>
        </label>

        <SegmentedControl
          ariaLabel={tr('训练模式', 'Training mode')}
          className="scenario-training-mode"
          value={mode}
          onValueChange={setMode}
          options={modeOptions.map((option) => ({
            label: getModeLabel(option, t),
            value: option,
          }))}
        />

        <SegmentedControl
          ariaLabel={tr('反馈模式', 'Feedback mode')}
          className="scenario-training-mode feedback"
          value={feedbackMode}
          onValueChange={setFeedbackMode}
          options={feedbackModeOptions.map((option) => ({
            label: getFeedbackModeLabel(option, tr),
            title: getFeedbackModeDescription(option, tr),
            value: option,
          }))}
        />
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
                <Button
                  type="button"
                  variant="primary"
                  className="scenario-training-start"
                  onClick={() => void startScenario(scenario)}
                  disabled={startingScenarioId !== null}
                >
                  {starting ? <Loader2 size={16} className="scenario-training-spin" /> : <Play size={16} />}
                  {starting ? t('common.starting') : t('common.startPractice')}
                </Button>
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
