import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
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
  DEFAULT_SCENARIO_DIMENSION_LOCALIZATION,
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
  getScenarioCategoryLabel,
  getScenarioDifficultyLabel,
  scenarioCategoryOptions,
  scenarioDifficultyOptions,
} from '../utils/scenarioLabels'
import {
  fetchScenarioConfig,
  saveScenarioConfig as saveRemoteScenarioConfig,
} from '../services/scenarioConfig'
import { SettingsShell } from './SettingsPage'
import { Button } from '../components/ui/button'
import { Checkbox } from '../components/ui/checkbox'
import { Input, Select, Textarea } from '../components/ui/form'
import { SegmentedControl, type SegmentedControlOption } from '../components/ui/segmented-control'
import './ScenarioConfigPage.css'

type ScenarioConfigTab = 'scenarios' | 'dimensions'
type ScenarioConfigNoticeTone = 'success' | 'info' | 'warning' | 'error'
type LocalizedText = readonly [zh: string, en: string]

interface ScenarioConfigNotice {
  tone: ScenarioConfigNoticeTone
  message: string
}

const frameworkOptions: Array<{ value: ScenarioConfigFramework; label: LocalizedText }> = [
  { value: 'prep', label: ['PREP', 'PREP'] },
  { value: 'star', label: ['STAR', 'STAR'] },
  { value: 'scqa', label: ['SCQA', 'SCQA'] },
  { value: 'pyramid', label: ['金字塔', 'Pyramid'] },
]

function translateLabel(label: LocalizedText, tr: TranslateInline): string {
  return tr(label[0], label[1])
}

function getDimensionDisplayName(dimension: ScenarioDimensionDefinition, tr: TranslateInline): string {
  const localization = DEFAULT_SCENARIO_DIMENSION_LOCALIZATION[dimension.id]
  return localization ? translateLabel(localization.name, tr) : dimension.name
}

function getDimensionDisplayDescription(dimension: ScenarioDimensionDefinition, tr: TranslateInline): string {
  const localization = DEFAULT_SCENARIO_DIMENSION_LOCALIZATION[dimension.id]
  return localization ? translateLabel(localization.description, tr) : dimension.description
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

function dimensionMatchesQuery(
  dimension: ScenarioDimensionDefinition,
  query: string,
  tr: TranslateInline,
): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [
    getDimensionDisplayName(dimension, tr),
    getDimensionDisplayDescription(dimension, tr),
    dimension.name,
    dimension.description,
    dimension.id,
  ].some((value) => value.toLowerCase().includes(needle))
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
        setNotice(null)
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

    return () => {
      active = false
    }
  }, [initialConfigState, syncDraftsFromState])

  const filteredScenarios = useMemo(
    () => state.scenarios.filter((scenario) => scenarioMatchesQuery(scenario, scenarioQuery)),
    [scenarioQuery, state.scenarios],
  )
  const filteredDimensions = useMemo(
    () => state.dimensions.filter((dimension) => dimensionMatchesQuery(dimension, dimensionQuery, tr)),
    [dimensionQuery, state.dimensions, tr],
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
  const tabOptions = useMemo<SegmentedControlOption<ScenarioConfigTab>[]>(
    () => [
      {
        value: 'scenarios',
        label: (
          <>
            <span className="scenario-config-tab-label">{tr('场景草稿', 'Scenario drafts')}</span>
            <span className="scenario-config-tab-count">{state.scenarios.length}</span>
          </>
        ),
      },
      {
        value: 'dimensions',
        label: (
          <>
            <span className="scenario-config-tab-label">{tr('维度库', 'Dimension library')}</span>
            <span className="scenario-config-tab-count">{state.dimensions.length}</span>
          </>
        ),
      },
    ],
    [state.dimensions.length, state.scenarios.length, tr],
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
    <SettingsShell activeTab="training">
      <div className="scenario-config-page" data-workbench-skin="training">
      <header className="scenario-config-header">
        <div>
          <div className="scenario-config-kicker">
            <SlidersHorizontal size={16} />
            <span>{tr('训练模板/评分', 'Templates / Rubrics')}</span>
          </div>
          <h1>{tr('训练场景与评分规则', 'Training scenarios and rubrics')}</h1>
          <p>{tr('统一管理可练习场景、评分维度与权重。', 'Manage practice scenarios, scoring dimensions, and weights.')}</p>
        </div>
        <div className="scenario-config-header-actions">
          <Button variant="secondary" onClick={createDimensionDraft} disabled={isRemoteSaving}>
            <Library size={16} />
            {tr('新建维度', 'New dimension')}
          </Button>
          <Button className="primary" variant="primary" onClick={createScenarioDraft} disabled={isRemoteSaving}>
            <Plus size={16} />
            {tr('新建场景', 'New scenario')}
          </Button>
        </div>
      </header>

      <section className="scenario-config-stats" aria-label={tr('场景配置概览', 'Scenario configuration summary')}>
        <div>
          <strong>{state.scenarios.length}</strong>
          <span>{tr('场景', 'Scenarios')}</span>
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

      {notice && (
        <div className={`scenario-config-notice ${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'}>
          {notice.tone === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{notice.message}</span>
        </div>
      )}

      <div className="scenario-config-tabbar">
        <SegmentedControl
          ariaLabel={tr('配置区域', 'Configuration areas')}
          className="scenario-config-tabs"
          onValueChange={setActiveTab}
          options={tabOptions}
          value={activeTab}
        />
      </div>

      {activeTab === 'scenarios' && (
        <main className="scenario-config-workspace">
          <aside className="scenario-config-list" aria-label={tr('场景草稿', 'Scenario drafts')}>
            <label className="scenario-config-search">
              <Search size={15} />
              <Input
                value={scenarioQuery}
                onChange={(event) => setScenarioQuery(event.target.value)}
                placeholder={tr('搜索场景草稿', 'Search scenario drafts')}
              />
            </label>

            <div className="scenario-config-list-items">
              {filteredScenarios.map((scenario) => {
                const validation = validateScenarioWeightTotal(scenario.dimensionWeights)
                return (
                  <Button
                    variant="ghost"
                    key={scenario.id}
                    className={scenario.id === draft.id ? 'selected' : ''}
                    onClick={() => selectScenario(scenario.id)}
                  >
                    <span className="scenario-config-row-title">{scenario.title}</span>
                    <span className="scenario-config-row-meta">
                      {getScenarioCategoryLabel(scenario.category, tr)} · {getScenarioDifficultyLabel(scenario.difficulty, tr)} · {validation.total}%
                    </span>
                    {!validation.valid && <span className="scenario-config-row-alert">{tr('需为 100%', 'Needs 100%')}</span>}
                  </Button>
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
              <Button className="scenario-config-save" variant="primary" onClick={saveScenarioDraft} disabled={isRemoteSaving}>
                <Save size={16} />
                {isRemoteSaving ? tr('保存中', 'Saving') : tr('保存草稿', 'Save draft')}
              </Button>
            </div>

            <div className="scenario-config-form-grid">
              <label>
                <span>{tr('场景名称', 'Scenario name')}</span>
                <Input value={draft.title} onChange={(event) => patchDraft({ title: event.target.value })} />
              </label>
              <label>
                <span>{tr('分类', 'Category')}</span>
                <Select
                  value={draft.category}
                  onChange={(event) => patchDraft({ category: event.target.value as ScenarioTrainingCategory })}
                >
                  {scenarioCategoryOptions.map((option) => (
                    <option key={option} value={option}>{getScenarioCategoryLabel(option, tr)}</option>
                  ))}
                </Select>
              </label>
              <label>
                <span>{tr('难度', 'Difficulty')}</span>
                <Select
                  value={draft.difficulty}
                  onChange={(event) => patchDraft({ difficulty: event.target.value as ScenarioTrainingDifficulty })}
                >
                  {scenarioDifficultyOptions.map((option) => (
                    <option key={option} value={option}>{getScenarioDifficultyLabel(option, tr)}</option>
                  ))}
                </Select>
              </label>
              <label>
                <span>{tr('表达框架', 'Framework')}</span>
                <Select
                  value={draft.framework}
                  onChange={(event) => patchDraft({ framework: event.target.value as ScenarioConfigFramework })}
                >
                  {frameworkOptions.map((option) => (
                    <option key={option.value} value={option.value}>{translateLabel(option.label, tr)}</option>
                  ))}
                </Select>
              </label>
              <label>
                <span>{tr('练习者角色', 'Learner role')}</span>
                <Input value={draft.learnerRole} onChange={(event) => patchDraft({ learnerRole: event.target.value })} />
              </label>
              <div className="scenario-config-switch-row">
                <span>{tr('标记', 'Flags')}</span>
                <div>
                  <label className={`scenario-config-check-option${draft.required ? ' selected' : ''}`}>
                    <Checkbox
                      checked={draft.required}
                      onChange={(event) => patchDraft({ required: event.target.checked })}
                    />
                    <span>{tr('必练', 'Required')}</span>
                  </label>
                  <label className={`scenario-config-check-option${draft.enabled ? ' selected' : ''}`}>
                    <Checkbox
                      checked={draft.enabled}
                      onChange={(event) => patchDraft({ enabled: event.target.checked })}
                    />
                    <span>{tr('启用', 'Enabled')}</span>
                  </label>
                </div>
              </div>
            </div>

            <label className="scenario-config-field">
              <span>{tr('场景描述', 'Scenario description')}</span>
              <Textarea
                value={draft.description}
                onChange={(event) => patchDraft({ description: event.target.value })}
                rows={3}
              />
            </label>

            <label className="scenario-config-field">
              <span>{tr('客户画像', 'Customer profile')}</span>
              <Textarea
                value={draft.customerProfile}
                onChange={(event) => patchDraft({ customerProfile: event.target.value })}
                rows={3}
              />
            </label>

            <label className="scenario-config-field">
              <span>{tr('对手开场白', 'Counterpart opening line')}</span>
              <Textarea
                value={draft.openingLine}
                onChange={(event) => patchDraft({ openingLine: event.target.value })}
                rows={2}
              />
            </label>

            <div className="scenario-config-form-grid">
              <label>
                <span>{tr('角色名称', 'Persona name')}</span>
                <Input value={draft.persona.name} onChange={(event) => updatePersona('name', event.target.value)} />
              </label>
              <label>
                <span>{tr('角色身份', 'Persona role')}</span>
                <Input value={draft.persona.role} onChange={(event) => updatePersona('role', event.target.value)} />
              </label>
            </div>

            <label className="scenario-config-field">
              <span>{tr('角色风格', 'Persona style')}</span>
              <Textarea
                value={draft.persona.style}
                onChange={(event) => updatePersona('style', event.target.value)}
                rows={2}
              />
            </label>

            <label className="scenario-config-field">
              <span>{tr('训练要点', 'Training points')}</span>
              <Textarea
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
                  <Button variant="secondary" size="sm" onClick={applyCategoryDefaults}>
                    <RotateCcw size={15} />
                    {tr('分类默认值', 'Category defaults')}
                  </Button>
                  <Button variant="secondary" size="sm" onClick={applyEvenWeights} disabled={draft.dimensionWeights.length === 0}>
                    <SlidersHorizontal size={15} />
                    {tr('平均分配', 'Even split')}
                  </Button>
                </div>
              </div>

              <div className="scenario-config-weight-meter" aria-label={tr('权重总和 {total}%', 'Weight total {total}%', { total: selectedWeightTotal })}>
                <span style={{ width: `${Math.min(100, selectedWeightTotal)}%` }} />
              </div>

              <div className="scenario-config-weight-table">
                {state.dimensions.map((dimension) => {
                  const selected = isDimensionSelected(dimension.id)
                  const weight = draft.dimensionWeights.find((item) => item.dimensionId === dimension.id)?.weight ?? 0
                  const displayName = getDimensionDisplayName(dimension, tr)
                  const displayDescription = getDimensionDisplayDescription(dimension, tr)
                  const disabled = !dimension.enabled && !selected
                  return (
                    <div key={dimension.id} className={!dimension.enabled ? 'disabled' : ''}>
                      <label
                        className={`scenario-config-weight-option${selected ? ' selected' : ''}${disabled ? ' disabled' : ''}`}
                      >
                        <Checkbox
                          checked={selected}
                          disabled={disabled}
                          onChange={() => toggleScenarioDimension(dimension.id)}
                        />
                        <span>{displayName}</span>
                      </label>
                      <p>{displayDescription || tr('暂无评分标准。', 'No scoring criteria yet.')}</p>
                      <label>
                        <Input
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
              <Input
                value={dimensionQuery}
                onChange={(event) => setDimensionQuery(event.target.value)}
                placeholder={tr('搜索维度', 'Search dimensions')}
              />
            </label>

            <div className="scenario-config-list-items">
              {filteredDimensions.map((dimension) => {
                const displayName = getDimensionDisplayName(dimension, tr)
                return (
                  <Button
                    variant="ghost"
                    key={dimension.id}
                    className={dimension.id === dimensionDraft.id ? 'selected' : ''}
                    onClick={() => selectDimension(dimension.id)}
                  >
                    <span className="scenario-config-row-title">{displayName}</span>
                    <span className="scenario-config-row-meta">
                      {dimension.enabled ? tr('已启用', 'Enabled') : tr('已禁用', 'Disabled')} · {tr('{count} 个引用', '{count} refs', {
                        count: dimensionRefs.get(dimension.id) ?? 0,
                      })}
                    </span>
                  </Button>
                )
              })}
            </div>
          </aside>

          <section className="scenario-config-editor" aria-label={tr('编辑所选维度', 'Edit selected dimension')}>
            <div className="scenario-config-editor-head">
              <div>
                <h2>{getDimensionDisplayName(dimensionDraft, tr) || tr('未命名维度', 'Untitled dimension')}</h2>
                <p>{dimensionDraft.id}</p>
              </div>
              <Button className="scenario-config-save" variant="primary" onClick={saveDimensionDraft} disabled={isRemoteSaving}>
                <Save size={16} />
                {isRemoteSaving ? tr('保存中', 'Saving') : tr('保存维度', 'Save dimension')}
              </Button>
            </div>

            <div className="scenario-config-form-grid">
              <label>
                <span>{tr('维度 ID', 'Dimension id')}</span>
                <Input
                  value={dimensionDraft.id}
                  disabled={Boolean(dimensionById.get(dimensionDraft.id))}
                  onChange={(event) => setDimensionDraft((current) => ({ ...current, id: event.target.value }))}
                />
              </label>
              <label>
                <span>{tr('维度名称', 'Dimension name')}</span>
                <Input
                  value={dimensionDraft.name}
                  onChange={(event) => setDimensionDraft((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
            </div>

            <label className="scenario-config-field">
              <span>{tr('评分标准', 'Scoring criteria')}</span>
              <Textarea
                value={dimensionDraft.description}
                onChange={(event) => setDimensionDraft((current) => ({ ...current, description: event.target.value }))}
                rows={6}
              />
            </label>

            <div className="scenario-config-dimension-footer">
              <Button variant="secondary" onClick={() => toggleDimensionEnabled(dimensionDraft)} disabled={isRemoteSaving}>
                {dimensionDraft.enabled ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                {dimensionDraft.enabled ? tr('对新场景禁用', 'Disable for new scenarios') : tr('启用维度', 'Enable dimension')}
              </Button>
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
    </SettingsShell>
  )
}
