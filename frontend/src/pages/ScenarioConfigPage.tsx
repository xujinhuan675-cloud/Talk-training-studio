import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Database,
  Library,
  Plus,
  RotateCcw,
  Save,
  Search,
  SlidersHorizontal,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react'
import {
  createBlankScenarioDraft,
  calculateScenarioWeightTotal,
  distributeScenarioWeights,
  getDefaultDimensionWeights,
  loadScenarioConfigState,
  normalizeScenarioWeight,
  saveScenarioConfigState,
  upsertScenarioConfigDraft,
  upsertScenarioDimension,
  validateScenarioWeightTotal,
  type ScenarioConfigDraft,
  type ScenarioConfigFramework,
  type ScenarioConfigState,
  type ScenarioDimensionDefinition,
} from '../data/scenarioConfig'
import {
  scenarioTrainingCatalog,
  type ScenarioTrainingCategory,
  type ScenarioTrainingDifficulty,
} from '../data/trainingScenarios'
import { useI18n, type Locale, type TranslateInline } from '../i18n'
import {
  fetchScenarioConfig,
  saveScenarioConfig as saveRemoteScenarioConfig,
} from '../services/scenarioConfig'
import './ScenarioConfigPage.css'

type ScenarioConfigTab = 'scenarios' | 'dimensions'
type ScenarioConfigNoticeTone = 'success' | 'info' | 'warning' | 'error'
type LocalizedText = readonly [zh: string, en: string]

interface ScenarioConfigNotice {
  tone: ScenarioConfigNoticeTone
  message: string
}

const categoryOptions: Array<{ value: ScenarioTrainingCategory; label: LocalizedText }> = [
  { value: 'sales', label: ['销售', 'Sales'] },
  { value: 'customer_service', label: ['客服', 'Customer service'] },
  { value: 'negotiation', label: ['谈判', 'Negotiation'] },
  { value: 'interview', label: ['面试', 'Interview'] },
]

const difficultyOptions: Array<{ value: ScenarioTrainingDifficulty; label: LocalizedText }> = [
  { value: 'easy', label: ['简单', 'Easy'] },
  { value: 'medium', label: ['中等', 'Medium'] },
  { value: 'hard', label: ['困难', 'Hard'] },
  { value: 'expert', label: ['专家', 'Expert'] },
]

const frameworkOptions: Array<{ value: ScenarioConfigFramework; label: LocalizedText }> = [
  { value: 'prep', label: ['PREP', 'PREP'] },
  { value: 'star', label: ['STAR', 'STAR'] },
  { value: 'scqa', label: ['SCQA', 'SCQA'] },
  { value: 'pyramid', label: ['金字塔', 'Pyramid'] },
]

function translateLabel(label: LocalizedText, tr: TranslateInline): string {
  return tr(label[0], label[1])
}

function getCategoryLabel(value: ScenarioTrainingCategory, tr: TranslateInline): string {
  return translateLabel(categoryOptions.find((option) => option.value === value)?.label ?? [value, value], tr)
}

function getDifficultyLabel(value: ScenarioTrainingDifficulty, tr: TranslateInline): string {
  return translateLabel(difficultyOptions.find((option) => option.value === value)?.label ?? [value, value], tr)
}

function getFrameworkLabel(value: ScenarioConfigFramework, tr: TranslateInline): string {
  return translateLabel(frameworkOptions.find((option) => option.value === value)?.label ?? [value, value], tr)
}

function formatDate(value: string | undefined, locale: Locale, tr: TranslateInline): string {
  if (!value) return tr('未保存', 'Not saved')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function splitLines(value: string): string[] {
  return value
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function createLocalDimension(name = 'New dimension'): ScenarioDimensionDefinition {
  const id = `local-dimension-${Date.now().toString(36)}`
  return {
    id,
    name,
    description: '',
    enabled: true,
    source: 'local',
    updatedAt: new Date().toISOString(),
  }
}

function scenarioMatchesQuery(scenario: ScenarioConfigDraft, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [
    scenario.title,
    scenario.description,
    scenario.customerProfile,
    scenario.persona.name,
    scenario.persona.role,
    scenario.learnerRole,
    ...scenario.trainingPoints,
  ].some((value) => value.toLowerCase().includes(needle))
}

function dimensionMatchesQuery(dimension: ScenarioDimensionDefinition, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [dimension.name, dimension.description, dimension.id].some((value) => value.toLowerCase().includes(needle))
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export default function ScenarioConfigPage() {
  const { locale, tr } = useI18n()
  const trRef = useRef(tr)
  const initialConfigState = useMemo(() => loadScenarioConfigState(scenarioTrainingCatalog), [])
  const [state, setState] = useState<ScenarioConfigState>(initialConfigState)
  const [activeTab, setActiveTab] = useState<ScenarioConfigTab>('scenarios')
  const [scenarioQuery, setScenarioQuery] = useState('')
  const [dimensionQuery, setDimensionQuery] = useState('')
  const [notice, setNotice] = useState<ScenarioConfigNotice | null>(null)
  const [isRemoteLoading, setIsRemoteLoading] = useState(true)
  const [isRemoteSaving, setIsRemoteSaving] = useState(false)

  const selectedScenario = useMemo(
    () => state.scenarios.find((scenario) => scenario.id === state.selectedScenarioId) ?? state.scenarios[0],
    [state.scenarios, state.selectedScenarioId],
  )
  const [draft, setDraft] = useState<ScenarioConfigDraft>(() => (
    selectedScenario ?? createBlankScenarioDraft()
  ))

  const selectedDimension = useMemo(
    () => state.dimensions.find((dimension) => dimension.id === state.selectedDimensionId) ?? state.dimensions[0],
    [state.dimensions, state.selectedDimensionId],
  )
  const [dimensionDraft, setDimensionDraft] = useState<ScenarioDimensionDefinition>(() => (
    selectedDimension ?? createLocalDimension(tr('新维度', 'New dimension'))
  ))

  const syncDraftsFromState = useCallback((nextState: ScenarioConfigState) => {
    setDraft(
      nextState.scenarios.find((scenario) => scenario.id === nextState.selectedScenarioId)
      ?? nextState.scenarios[0]
      ?? createBlankScenarioDraft(),
    )
    setDimensionDraft(
      nextState.dimensions.find((dimension) => dimension.id === nextState.selectedDimensionId)
      ?? nextState.dimensions[0]
      ?? createLocalDimension(trRef.current('新维度', 'New dimension')),
    )
  }, [])

  useEffect(() => {
    trRef.current = tr
  }, [tr])

  useEffect(() => {
    let active = true

    setIsRemoteLoading(true)
    setNotice({
      tone: 'info',
      message: trRef.current('正在从后端加载场景配置。', 'Loading scenario config from backend.'),
    })

    fetchScenarioConfig(scenarioTrainingCatalog, initialConfigState)
      .then((remoteState) => {
        if (!active) return
        setState(remoteState)
        saveScenarioConfigState(remoteState)
        syncDraftsFromState(remoteState)
        setNotice({
          tone: 'success',
          message: trRef.current('已从后端加载场景配置。', 'Loaded scenario config from backend.'),
        })
      })
      .catch((error: unknown) => {
        if (!active) return
        setNotice({
          tone: 'warning',
          message: trRef.current(
            '后端配置暂不可用，继续使用本地草稿。{message}',
            'Backend config is unavailable; continuing with local drafts. {message}',
            { message: getErrorMessage(error) },
          ),
        })
      })
      .finally(() => {
        if (active) {
          setIsRemoteLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [initialConfigState, syncDraftsFromState])

  const filteredScenarios = useMemo(
    () => state.scenarios.filter((scenario) => scenarioMatchesQuery(scenario, scenarioQuery)),
    [scenarioQuery, state.scenarios],
  )
  const filteredDimensions = useMemo(
    () => state.dimensions.filter((dimension) => dimensionMatchesQuery(dimension, dimensionQuery)),
    [dimensionQuery, state.dimensions],
  )
  const enabledDimensions = useMemo(
    () => state.dimensions.filter((dimension) => dimension.enabled),
    [state.dimensions],
  )
  const dimensionRefs = useMemo(() => {
    const refs = new Map<string, number>()
    state.scenarios.forEach((scenario) => {
      scenario.dimensionWeights.forEach((item) => {
        refs.set(item.dimensionId, (refs.get(item.dimensionId) ?? 0) + 1)
      })
    })
    return refs
  }, [state.scenarios])
  const invalidScenarioCount = useMemo(
    () => state.scenarios.filter((scenario) => !validateScenarioWeightTotal(scenario.dimensionWeights).valid).length,
    [state.scenarios],
  )
  const selectedWeightValidation = validateScenarioWeightTotal(draft.dimensionWeights)
  const selectedWeightTotal = calculateScenarioWeightTotal(draft.dimensionWeights)

  const formatWeightValidationMessage = (validation = selectedWeightValidation): string => {
    if (validation.selectedCount === 0) {
      return tr('至少选择一个评分维度。', 'Select at least one scoring dimension.')
    }
    if (validation.valid) {
      return tr('权重总和为 100%。', 'Weight total is 100%.')
    }
    return tr('权重总和必须等于 100%。当前为 {total}%。', 'Weight total must equal 100%. Current total is {total}%.', {
      total: validation.total,
    })
  }

  const persistState = async (nextState: ScenarioConfigState, successMessage?: string) => {
    setState(nextState)
    saveScenarioConfigState(nextState)
    setIsRemoteSaving(true)
    setNotice({
      tone: 'info',
      message: tr('正在保存到后端，本地草稿已先保留。', 'Saving to backend; local draft has already been kept.'),
    })

    try {
      const remoteState = await saveRemoteScenarioConfig(nextState, scenarioTrainingCatalog)
      setState(remoteState)
      saveScenarioConfigState(remoteState)
      setNotice({
        tone: 'success',
        message: successMessage ?? tr('已保存到后端。', 'Saved to backend.'),
      })
    } catch (error: unknown) {
      setNotice({
        tone: 'error',
        message: tr(
          '后端保存失败，本地草稿已保留。{message}',
          'Backend save failed; local draft was kept. {message}',
          { message: getErrorMessage(error) },
        ),
      })
    } finally {
      setIsRemoteSaving(false)
    }
  }

  const selectScenario = (scenarioId: string) => {
    const nextScenario = state.scenarios.find((scenario) => scenario.id === scenarioId)
    if (nextScenario) {
      setDraft(nextScenario)
    }
    setState((current) => ({
      ...current,
      selectedScenarioId: scenarioId,
    }))
  }

  const selectDimension = (dimensionId: string) => {
    const nextDimension = state.dimensions.find((dimension) => dimension.id === dimensionId)
    if (nextDimension) {
      setDimensionDraft(nextDimension)
    }
    setState((current) => ({
      ...current,
      selectedDimensionId: dimensionId,
    }))
  }

  const patchDraft = (patch: Partial<ScenarioConfigDraft>) => {
    setDraft((current) => ({
      ...current,
      ...patch,
    }))
  }

  const updatePersona = (key: keyof ScenarioConfigDraft['persona'], value: string) => {
    setDraft((current) => ({
      ...current,
      persona: {
        ...current.persona,
        [key]: value,
      },
    }))
  }

  const isDimensionSelected = (dimensionId: string) => (
    draft.dimensionWeights.some((item) => item.dimensionId === dimensionId)
  )

  const toggleScenarioDimension = (dimensionId: string) => {
    setDraft((current) => {
      const selected = current.dimensionWeights.some((item) => item.dimensionId === dimensionId)
      return {
        ...current,
        dimensionWeights: selected
          ? current.dimensionWeights.filter((item) => item.dimensionId !== dimensionId)
          : [...current.dimensionWeights, { dimensionId, weight: 0 }],
      }
    })
  }

  const updateScenarioWeight = (dimensionId: string, value: string) => {
    setDraft((current) => ({
      ...current,
      dimensionWeights: current.dimensionWeights.map((item) => (
        item.dimensionId === dimensionId
          ? { ...item, weight: normalizeScenarioWeight(value) }
          : item
      )),
    }))
  }

  const applyEvenWeights = () => {
    setDraft((current) => ({
      ...current,
      dimensionWeights: distributeScenarioWeights(current.dimensionWeights.map((item) => item.dimensionId)),
    }))
  }

  const applyCategoryDefaults = () => {
    setDraft((current) => ({
      ...current,
      dimensionWeights: getDefaultDimensionWeights(current.category),
    }))
  }

  const saveScenarioDraft = () => {
    const validation = validateScenarioWeightTotal(draft.dimensionWeights)
    if (!draft.title.trim()) {
      setNotice({ tone: 'warning', message: tr('场景名称不能为空。', 'Scenario name is required.') })
      return
    }
    if (!validation.valid) {
      setNotice({ tone: 'warning', message: formatWeightValidationMessage(validation) })
      return
    }
    void persistState(upsertScenarioConfigDraft(state, draft))
  }

  const createScenarioDraft = () => {
    const nextDraft = createBlankScenarioDraft({
      title: tr('新的本地场景', 'New local scenario'),
      dimensionWeights: getDefaultDimensionWeights('sales'),
    })
    setDraft(nextDraft)
    void persistState(upsertScenarioConfigDraft(state, nextDraft), tr('新的场景草稿已保存到后端。', 'New draft saved to backend.'))
    setActiveTab('scenarios')
  }

  const saveDimensionDraft = () => {
    if (!dimensionDraft.id.trim() || !dimensionDraft.name.trim()) {
      setNotice({ tone: 'warning', message: tr('维度 ID 和名称不能为空。', 'Dimension id and name are required.') })
      return
    }
    void persistState(upsertScenarioDimension(state, dimensionDraft), tr('维度已保存到后端。', 'Dimension saved to backend.'))
  }

  const createDimensionDraft = () => {
    const nextDimension = createLocalDimension(tr('新维度', 'New dimension'))
    setDimensionDraft(nextDimension)
    void persistState(upsertScenarioDimension(state, nextDimension), tr('新的维度已保存到后端。', 'New dimension saved to backend.'))
    setActiveTab('dimensions')
  }

  const toggleDimensionEnabled = (dimension: ScenarioDimensionDefinition) => {
    const nextDimension = {
      ...dimension,
      enabled: !dimension.enabled,
    }
    setDimensionDraft((current) => current.id === nextDimension.id ? nextDimension : current)
    void persistState(
      upsertScenarioDimension(state, nextDimension),
      dimension.enabled
        ? tr('该维度已禁用并保存到后端。', 'Dimension disabled and saved to backend.')
        : tr('该维度已启用并保存到后端。', 'Dimension enabled and saved to backend.'),
    )
  }

  const dimensionById = new Map(state.dimensions.map((dimension) => [dimension.id, dimension]))

  return (
    <div className="scenario-config-page">
      <header className="scenario-config-header">
        <div>
          <div className="scenario-config-kicker">
            <SlidersHorizontal size={16} />
            <span>{tr('场景管理配置', 'Scenario Admin Config')}</span>
          </div>
          <h1>{tr('场景草稿与评分规则', 'Scenario drafts and scoring rubrics')}</h1>
          <p>
            {tr(
              '优先同步后端场景配置，同时保留本地草稿兜底，管理可复用评分维度库和每个场景的评分权重。',
              'Sync scenario config from the backend first while keeping local drafts as fallback, including reusable dimensions and per-scenario scoring weights.',
            )}
          </p>
        </div>
        <div className="scenario-config-header-actions">
          <button type="button" onClick={createDimensionDraft} disabled={isRemoteSaving}>
            <Library size={16} />
            {tr('新建维度', 'New dimension')}
          </button>
          <button type="button" className="primary" onClick={createScenarioDraft} disabled={isRemoteSaving}>
            <Plus size={16} />
            {tr('新建场景', 'New scenario')}
          </button>
        </div>
      </header>

      <section className="scenario-config-stats" aria-label={tr('场景配置概览', 'Scenario configuration summary')}>
        <div>
          <strong>{state.scenarios.length}</strong>
          <span>{tr('本地草稿', 'Local drafts')}</span>
        </div>
        <div>
          <strong>{enabledDimensions.length}/{state.dimensions.length}</strong>
          <span>{tr('已启用维度', 'Enabled dimensions')}</span>
        </div>
        <div className={invalidScenarioCount ? 'warning' : 'ok'}>
          <strong>{invalidScenarioCount}</strong>
          <span>{tr('权重问题', 'Weight issues')}</span>
        </div>
        <div>
          <strong>{formatDate(state.updatedAt, locale, tr)}</strong>
          <span>{tr('最近配置修改', 'Last config change')}</span>
        </div>
      </section>

      <section className="scenario-config-api-note">
        <Database size={16} />
        <span>
          {isRemoteLoading
            ? tr('正在连接后端配置接口：', 'Connecting to backend config API: ')
            : isRemoteSaving
              ? tr('正在写入后端配置接口：', 'Writing backend config API: ')
              : tr('后端优先同步接口：', 'Backend-first sync API: ')}
          <code>GET/PUT /api/v1/training-studio/scenario-config</code>
          {tr('；后端不可用时继续使用 localStorage 草稿。', '; localStorage drafts remain available when the backend is unavailable.')}
        </span>
      </section>

      {notice && (
        <div className={`scenario-config-notice ${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'}>
          {notice.tone === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{notice.message}</span>
        </div>
      )}

      <div className="scenario-config-tabbar">
        <div className="scenario-config-tabs" role="tablist" aria-label={tr('配置区域', 'Configuration areas')}>
          <button
            type="button"
            className={activeTab === 'scenarios' ? 'selected' : ''}
            onClick={() => setActiveTab('scenarios')}
          >
            {tr('场景草稿', 'Scenario drafts')}
            <span>{state.scenarios.length}</span>
          </button>
          <button
            type="button"
            className={activeTab === 'dimensions' ? 'selected' : ''}
            onClick={() => setActiveTab('dimensions')}
          >
            {tr('维度库', 'Dimension library')}
            <span>{state.dimensions.length}</span>
          </button>
        </div>
      </div>

      {activeTab === 'scenarios' && (
        <main className="scenario-config-workspace">
          <aside className="scenario-config-list" aria-label={tr('场景草稿', 'Scenario drafts')}>
            <label className="scenario-config-search">
              <Search size={15} />
              <input
                value={scenarioQuery}
                onChange={(event) => setScenarioQuery(event.target.value)}
                placeholder={tr('搜索场景草稿', 'Search scenario drafts')}
              />
            </label>

            <div className="scenario-config-list-items">
              {filteredScenarios.map((scenario) => {
                const validation = validateScenarioWeightTotal(scenario.dimensionWeights)
                return (
                  <button
                    type="button"
                    key={scenario.id}
                    className={scenario.id === draft.id ? 'selected' : ''}
                    onClick={() => selectScenario(scenario.id)}
                  >
                    <span className="scenario-config-row-title">{scenario.title}</span>
                    <span className="scenario-config-row-meta">
                      {getCategoryLabel(scenario.category, tr)} · {getDifficultyLabel(scenario.difficulty, tr)} · {validation.total}%
                    </span>
                    {!validation.valid && <span className="scenario-config-row-alert">{tr('需为 100%', 'Needs 100%')}</span>}
                  </button>
                )
              })}
            </div>
          </aside>

          <section className="scenario-config-editor" aria-label={tr('编辑所选场景', 'Edit selected scenario')}>
            <div className="scenario-config-editor-head">
              <div>
                <h2>{draft.title || tr('未命名场景', 'Untitled scenario')}</h2>
                <p>{draft.id} · {getFrameworkLabel(draft.framework, tr)}</p>
              </div>
              <button type="button" className="scenario-config-save" onClick={saveScenarioDraft} disabled={isRemoteSaving}>
                <Save size={16} />
                {isRemoteSaving ? tr('保存中', 'Saving') : tr('保存草稿', 'Save draft')}
              </button>
            </div>

            <div className="scenario-config-form-grid">
              <label>
                <span>{tr('场景名称', 'Scenario name')}</span>
                <input value={draft.title} onChange={(event) => patchDraft({ title: event.target.value })} />
              </label>
              <label>
                <span>{tr('分类', 'Category')}</span>
                <select
                  value={draft.category}
                  onChange={(event) => patchDraft({ category: event.target.value as ScenarioTrainingCategory })}
                >
                  {categoryOptions.map((option) => (
                    <option key={option.value} value={option.value}>{translateLabel(option.label, tr)}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{tr('难度', 'Difficulty')}</span>
                <select
                  value={draft.difficulty}
                  onChange={(event) => patchDraft({ difficulty: event.target.value as ScenarioTrainingDifficulty })}
                >
                  {difficultyOptions.map((option) => (
                    <option key={option.value} value={option.value}>{translateLabel(option.label, tr)}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{tr('表达框架', 'Framework')}</span>
                <select
                  value={draft.framework}
                  onChange={(event) => patchDraft({ framework: event.target.value as ScenarioConfigFramework })}
                >
                  {frameworkOptions.map((option) => (
                    <option key={option.value} value={option.value}>{translateLabel(option.label, tr)}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{tr('练习者角色', 'Learner role')}</span>
                <input value={draft.learnerRole} onChange={(event) => patchDraft({ learnerRole: event.target.value })} />
              </label>
              <label className="scenario-config-switch-row">
                <span>{tr('标记', 'Flags')}</span>
                <div>
                  <button
                    type="button"
                    className={draft.required ? 'selected' : ''}
                    onClick={() => patchDraft({ required: !draft.required })}
                  >
                    {tr('必练', 'Required')}
                  </button>
                  <button
                    type="button"
                    className={draft.enabled ? 'selected' : ''}
                    onClick={() => patchDraft({ enabled: !draft.enabled })}
                  >
                    {tr('启用', 'Enabled')}
                  </button>
                </div>
              </label>
            </div>

            <label className="scenario-config-field">
              <span>{tr('场景描述', 'Scenario description')}</span>
              <textarea
                value={draft.description}
                onChange={(event) => patchDraft({ description: event.target.value })}
                rows={3}
              />
            </label>

            <label className="scenario-config-field">
              <span>{tr('客户画像', 'Customer profile')}</span>
              <textarea
                value={draft.customerProfile}
                onChange={(event) => patchDraft({ customerProfile: event.target.value })}
                rows={3}
              />
            </label>

            <label className="scenario-config-field">
              <span>{tr('对手开场白', 'Counterpart opening line')}</span>
              <textarea
                value={draft.openingLine}
                onChange={(event) => patchDraft({ openingLine: event.target.value })}
                rows={2}
              />
            </label>

            <div className="scenario-config-form-grid">
              <label>
                <span>{tr('角色名称', 'Persona name')}</span>
                <input value={draft.persona.name} onChange={(event) => updatePersona('name', event.target.value)} />
              </label>
              <label>
                <span>{tr('角色身份', 'Persona role')}</span>
                <input value={draft.persona.role} onChange={(event) => updatePersona('role', event.target.value)} />
              </label>
            </div>

            <label className="scenario-config-field">
              <span>{tr('角色风格', 'Persona style')}</span>
              <textarea
                value={draft.persona.style}
                onChange={(event) => updatePersona('style', event.target.value)}
                rows={2}
              />
            </label>

            <label className="scenario-config-field">
              <span>{tr('训练要点', 'Training points')}</span>
              <textarea
                value={draft.trainingPoints.join('\n')}
                onChange={(event) => patchDraft({ trainingPoints: splitLines(event.target.value) })}
                rows={4}
                placeholder={tr('每行一个训练要点', 'One training point per line')}
              />
            </label>

            <section className="scenario-config-weight-editor" aria-label={tr('场景评分维度权重', 'Scenario dimension weights')}>
              <div className="scenario-config-weight-head">
                <div>
                  <h3>{tr('评分维度与权重', 'Scoring dimensions and weights')}</h3>
                  <p className={selectedWeightValidation.valid ? 'ok' : 'warning'}>
                    {formatWeightValidationMessage()}
                  </p>
                </div>
                <div>
                  <button type="button" onClick={applyCategoryDefaults}>
                    <RotateCcw size={15} />
                    {tr('分类默认值', 'Category defaults')}
                  </button>
                  <button type="button" onClick={applyEvenWeights} disabled={draft.dimensionWeights.length === 0}>
                    <SlidersHorizontal size={15} />
                    {tr('平均分配', 'Even split')}
                  </button>
                </div>
              </div>

              <div className="scenario-config-weight-meter" aria-label={tr('权重总和 {total}%', 'Weight total {total}%', { total: selectedWeightTotal })}>
                <span style={{ width: `${Math.min(100, selectedWeightTotal)}%` }} />
              </div>

              <div className="scenario-config-weight-table">
                {state.dimensions.map((dimension) => {
                  const selected = isDimensionSelected(dimension.id)
                  const weight = draft.dimensionWeights.find((item) => item.dimensionId === dimension.id)?.weight ?? 0
                  return (
                    <div key={dimension.id} className={!dimension.enabled ? 'disabled' : ''}>
                      <button
                        type="button"
                        className={selected ? 'selected' : ''}
                        onClick={() => toggleScenarioDimension(dimension.id)}
                        disabled={!dimension.enabled && !selected}
                      >
                        {selected ? <CheckCircle2 size={15} /> : <Plus size={15} />}
                        <span>{dimension.name}</span>
                      </button>
                      <p>{dimension.description || tr('暂无评分标准。', 'No scoring criteria yet.')}</p>
                      <label>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          value={weight}
                          disabled={!selected}
                          onChange={(event) => updateScenarioWeight(dimension.id, event.target.value)}
                        />
                        <span>%</span>
                      </label>
                    </div>
                  )
                })}
              </div>
            </section>
          </section>
        </main>
      )}

      {activeTab === 'dimensions' && (
        <main className="scenario-config-workspace">
          <aside className="scenario-config-list" aria-label={tr('维度库', 'Dimension library')}>
            <label className="scenario-config-search">
              <Search size={15} />
              <input
                value={dimensionQuery}
                onChange={(event) => setDimensionQuery(event.target.value)}
                placeholder={tr('搜索维度', 'Search dimensions')}
              />
            </label>

            <div className="scenario-config-list-items">
              {filteredDimensions.map((dimension) => (
                <button
                  type="button"
                  key={dimension.id}
                  className={dimension.id === dimensionDraft.id ? 'selected' : ''}
                  onClick={() => selectDimension(dimension.id)}
                >
                  <span className="scenario-config-row-title">{dimension.name}</span>
                  <span className="scenario-config-row-meta">
                    {dimension.enabled ? tr('已启用', 'Enabled') : tr('已禁用', 'Disabled')} · {tr('{count} 个引用', '{count} refs', {
                      count: dimensionRefs.get(dimension.id) ?? 0,
                    })}
                  </span>
                </button>
              ))}
            </div>
          </aside>

          <section className="scenario-config-editor" aria-label={tr('编辑所选维度', 'Edit selected dimension')}>
            <div className="scenario-config-editor-head">
              <div>
                <h2>{dimensionDraft.name || tr('未命名维度', 'Untitled dimension')}</h2>
                <p>{dimensionDraft.id}</p>
              </div>
              <button type="button" className="scenario-config-save" onClick={saveDimensionDraft} disabled={isRemoteSaving}>
                <Save size={16} />
                {isRemoteSaving ? tr('保存中', 'Saving') : tr('保存维度', 'Save dimension')}
              </button>
            </div>

            <div className="scenario-config-form-grid">
              <label>
                <span>{tr('维度 ID', 'Dimension id')}</span>
                <input
                  value={dimensionDraft.id}
                  disabled={Boolean(dimensionById.get(dimensionDraft.id))}
                  onChange={(event) => setDimensionDraft((current) => ({ ...current, id: event.target.value }))}
                />
              </label>
              <label>
                <span>{tr('维度名称', 'Dimension name')}</span>
                <input
                  value={dimensionDraft.name}
                  onChange={(event) => setDimensionDraft((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
            </div>

            <label className="scenario-config-field">
              <span>{tr('评分标准', 'Scoring criteria')}</span>
              <textarea
                value={dimensionDraft.description}
                onChange={(event) => setDimensionDraft((current) => ({ ...current, description: event.target.value }))}
                rows={6}
              />
            </label>

            <div className="scenario-config-dimension-footer">
              <button type="button" onClick={() => toggleDimensionEnabled(dimensionDraft)} disabled={isRemoteSaving}>
                {dimensionDraft.enabled ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                {dimensionDraft.enabled ? tr('对新场景禁用', 'Disable for new scenarios') : tr('启用维度', 'Enable dimension')}
              </button>
              <span>
                {tr(
                  '已被 {count} 个本地场景草稿引用。已禁用维度仍会显示在已使用它的草稿中。',
                  'Referenced by {count} local scenario drafts. Disabled dimensions remain visible on drafts that already use them.',
                  { count: dimensionRefs.get(dimensionDraft.id) ?? 0 },
                )}
              </span>
            </div>
          </section>
        </main>
      )}
    </div>
  )
}
