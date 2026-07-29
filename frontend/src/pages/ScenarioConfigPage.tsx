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
  Trash2,
} from 'lucide-react'
import {
  createBlankScenarioDraft,
  calculateScenarioWeightTotal,
  DEFAULT_SCENARIO_DIMENSION_LOCALIZATION,
  distributeScenarioWeights,
  getDefaultDimensionWeights,
  loadScenarioConfigState,
  normalizeScenarioWeight,
  removeScenarioConfigDraft,
  removeScenarioDimension,
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
import { useI18n, type TranslateInline } from '../i18n'
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
import { PageHeader } from '../components/ui/page'
import { SegmentedControl, type SegmentedControlOption } from '../components/ui/segmented-control'
import { Surface } from '../components/ui/surface'
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
  const { tr } = useI18n()
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
  const dimensionRefs = useMemo(() => {
    const refs = new Map<string, number>()
    state.scenarios.forEach((scenario) => {
      scenario.dimensionWeights.forEach((item) => {
        refs.set(item.dimensionId, (refs.get(item.dimensionId) ?? 0) + 1)
      })
    })
    return refs
  }, [state.scenarios])
  const tabOptions = useMemo<SegmentedControlOption<ScenarioConfigTab>[]>(
    () => [
      {
        value: 'scenarios',
        label: <span className="scenario-config-tab-label">{tr('场景草稿', 'Scenario drafts')}</span>,
      },
      {
        value: 'dimensions',
        label: <span className="scenario-config-tab-label">{tr('维度库', 'Dimension library')}</span>,
      },
    ],
    [tr],
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

  const deleteScenarioDraft = () => {
    const title = draft.title.trim() || tr('未命名场景', 'Untitled scenario')
    const confirmed = window.confirm(tr(
      '删除场景草稿「{title}」？此操作会同步保存。',
      'Delete scenario draft "{title}"? This will be saved.',
      { title },
    ))
    if (!confirmed) return

    const nextState = removeScenarioConfigDraft(state, draft.id)
    if (nextState === state) return

    setDraft(
      nextState.scenarios.find((scenario) => scenario.id === nextState.selectedScenarioId)
      ?? nextState.scenarios[0]
      ?? createBlankScenarioDraft({ title: tr('新的本地场景', 'New local scenario') }),
    )
    void persistState(nextState, tr('场景草稿已删除。', 'Scenario draft deleted.'))
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

  const deleteDimensionDraft = () => {
    const name = getDimensionDisplayName(dimensionDraft, tr) || tr('未命名维度', 'Untitled dimension')
    if (dimensionDraft.source !== 'local') {
      setNotice({
        tone: 'warning',
        message: tr('默认评分维度不能删除，请使用禁用。', 'Default scoring dimensions cannot be deleted. Disable them instead.'),
      })
      return
    }

    const refCount = dimensionRefs.get(dimensionDraft.id) ?? 0
    const confirmed = window.confirm(refCount > 0
      ? tr(
        '删除维度「{name}」？它会从 {count} 个场景的评分权重中移除，并按剩余维度重算权重。',
        'Delete dimension "{name}"? It will be removed from {count} scenario weight set(s), and remaining weights will be rebalanced.',
        { name, count: refCount },
      )
      : tr(
        '删除维度「{name}」？此操作会同步保存。',
        'Delete dimension "{name}"? This will be saved.',
        { name },
      ))
    if (!confirmed) return

    const nextState = removeScenarioDimension(state, dimensionDraft.id)
    if (nextState === state) return

    setDimensionDraft(
      nextState.dimensions.find((dimension) => dimension.id === nextState.selectedDimensionId)
      ?? nextState.dimensions[0]
      ?? createLocalDimension(tr('新维度', 'New dimension')),
    )
    setDraft(
      nextState.scenarios.find((scenario) => scenario.id === draft.id)
      ?? nextState.scenarios.find((scenario) => scenario.id === nextState.selectedScenarioId)
      ?? nextState.scenarios[0]
      ?? createBlankScenarioDraft({ title: tr('新的本地场景', 'New local scenario') }),
    )
    void persistState(nextState, tr('维度已删除。', 'Dimension deleted.'))
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
    <SettingsShell activeTab="training" canUseManagementTabs={true}>
      <div className="scenario-config-page" data-workbench-skin="training">
      <PageHeader
        className="scenario-config-header"
        title={tr('训练场景与评分规则', 'Training scenarios and rubrics')}
        description={tr('统一管理可练习场景、评分维度与权重。', 'Manage practice scenarios, scoring dimensions, and weights.')}
        actions={(
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
        )}
      />

      {notice && (
        <Surface
          as="div"
          className={`scenario-config-notice ${notice.tone}`}
          padding="sm"
          role={notice.tone === 'error' ? 'alert' : 'status'}
        >
          {notice.tone === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{notice.message}</span>
        </Surface>
      )}

      <Surface as="div" className="scenario-config-tabbar" padding="sm">
        <SegmentedControl
          ariaLabel={tr('配置区域', 'Configuration areas')}
          className="scenario-config-tabs"
          onValueChange={setActiveTab}
          options={tabOptions}
          size="sm"
          value={activeTab}
        />
      </Surface>

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
              <div className="scenario-config-editor-actions">
                <Button
                  className="scenario-config-delete"
                  variant="secondary"
                  onClick={deleteScenarioDraft}
                  disabled={isRemoteSaving || state.scenarios.length === 0}
                >
                  <Trash2 size={16} />
                  {tr('删除草稿', 'Delete draft')}
                </Button>
                <Button className="scenario-config-save" variant="primary" onClick={saveScenarioDraft} disabled={isRemoteSaving}>
                  <Save size={16} />
                  {isRemoteSaving ? tr('保存中', 'Saving') : tr('保存草稿', 'Save draft')}
                </Button>
              </div>
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

            <details className="scenario-config-section scenario-config-content-section">
              <summary className="scenario-config-section-summary">
                <span>
                  <strong>{tr('场景内容', 'Scenario content')}</strong>
                  <small>{tr('目标、背景、角色和训练要点', 'Goals, context, persona, and training points')}</small>
                </span>
              </summary>

              <div className="scenario-config-section-body">
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
              </div>
            </details>

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

              <details className="scenario-config-section scenario-config-weight-details">
                <summary className="scenario-config-section-summary">
                  <span>
                    <strong>{tr('权重明细', 'Weight details')}</strong>
                    <small>
                      {tr('{count} 个维度', '{count} dimensions', { count: draft.dimensionWeights.length })}
                    </small>
                  </span>
                </summary>

                <div className="scenario-config-section-body scenario-config-weight-table">
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
              </details>
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
              <div className="scenario-config-editor-actions">
                <Button
                  className="scenario-config-delete"
                  variant="secondary"
                  onClick={deleteDimensionDraft}
                  disabled={isRemoteSaving || !dimensionDraft.id.trim()}
                >
                  <Trash2 size={16} />
                  {tr('删除维度', 'Delete dimension')}
                </Button>
                <Button className="scenario-config-save" variant="primary" onClick={saveDimensionDraft} disabled={isRemoteSaving}>
                  <Save size={16} />
                  {isRemoteSaving ? tr('保存中', 'Saving') : tr('保存维度', 'Save dimension')}
                </Button>
              </div>
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

            <details className="scenario-config-section scenario-config-dimension-criteria">
              <summary className="scenario-config-section-summary">
                <span>
                  <strong>{tr('标准定义', 'Criteria definition')}</strong>
                  <small>
                    {dimensionDraft.description.trim()
                      ? tr('已填写评分标准', 'Scoring criteria added')
                      : tr('待补充评分标准', 'Scoring criteria pending')}
                  </small>
                </span>
              </summary>

              <div className="scenario-config-section-body">
                <label className="scenario-config-field">
                  <span>{tr('评分标准', 'Scoring criteria')}</span>
                  <Textarea
                    value={dimensionDraft.description}
                    onChange={(event) => setDimensionDraft((current) => ({ ...current, description: event.target.value }))}
                    rows={6}
                  />
                </label>
              </div>
            </details>

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
