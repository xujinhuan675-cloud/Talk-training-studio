import type {
  ScenarioTrainingCard,
  ScenarioTrainingCategory,
  ScenarioTrainingDifficulty,
} from './trainingScenarios'

export type ScenarioConfigFramework = ScenarioTrainingCard['framework']

export interface ScenarioDimensionDefinition {
  id: string
  name: string
  description: string
  enabled: boolean
  updatedAt: string
  source?: 'default' | 'local'
}

export interface ScenarioDimensionWeight {
  dimensionId: string
  weight: number
}

export interface ScenarioConfigDraft {
  id: string
  title: string
  description: string
  customerProfile: string
  difficulty: ScenarioTrainingDifficulty
  category: ScenarioTrainingCategory
  required: boolean
  enabled: boolean
  openingLine: string
  persona: {
    name: string
    role: string
    style: string
  }
  learnerRole: string
  framework: ScenarioConfigFramework
  trainingPoints: string[]
  dimensionWeights: ScenarioDimensionWeight[]
  sourceScenarioId?: string
  updatedAt: string
}

export interface ScenarioConfigState {
  version: 1
  dimensions: ScenarioDimensionDefinition[]
  scenarios: ScenarioConfigDraft[]
  selectedScenarioId?: string
  selectedDimensionId?: string
  updatedAt: string
}

export interface ScenarioWeightValidation {
  total: number
  selectedCount: number
  valid: boolean
  message: string
}

export type ScenarioDimensionLocalizedText = readonly [zh: string, en: string]

export interface ScenarioDimensionLocalization {
  name: ScenarioDimensionLocalizedText
  description: ScenarioDimensionLocalizedText
}

export const SCENARIO_CONFIG_STORAGE_KEY = 'talkwise.scenarioConfig.v1'

export const DEFAULT_SCENARIO_DIMENSIONS: ScenarioDimensionDefinition[] = [
  {
    id: 'substance',
    name: 'Substance',
    description: 'The answer addresses the real business issue with concrete information, clear trade-offs, and useful next steps.',
    enabled: true,
    source: 'default',
    updatedAt: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'structure',
    name: 'Structure',
    description: 'The response is easy to follow, uses an appropriate framework, and keeps the conversation moving without rambling.',
    enabled: true,
    source: 'default',
    updatedAt: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'relevance',
    name: 'Relevance',
    description: 'The learner listens to the counterpart, responds to the actual objection or need, and avoids generic scripts.',
    enabled: true,
    source: 'default',
    updatedAt: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'credibility',
    name: 'Credibility',
    description: 'Claims are supported by evidence, examples, limitations, or a believable implementation plan.',
    enabled: true,
    source: 'default',
    updatedAt: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'differentiation',
    name: 'Differentiation',
    description: 'The answer creates a clear point of view, useful contrast, or differentiated value instead of sounding interchangeable.',
    enabled: true,
    source: 'default',
    updatedAt: '2026-01-01T00:00:00.000Z',
  },
]

export const DEFAULT_SCENARIO_DIMENSION_LOCALIZATION: Record<string, ScenarioDimensionLocalization> = {
  substance: {
    name: ['内容质量', 'Substance'],
    description: [
      '回答是否抓住真实业务问题，提供具体信息、清晰取舍和可执行下一步。',
      'The answer addresses the real business issue with concrete information, clear trade-offs, and useful next steps.',
    ],
  },
  structure: {
    name: ['表达结构', 'Structure'],
    description: [
      '表达是否易于跟随，能使用合适框架，并在不跑题的情况下推动对话。',
      'The response is easy to follow, uses an appropriate framework, and keeps the conversation moving without rambling.',
    ],
  },
  relevance: {
    name: ['回应相关性', 'Relevance'],
    description: [
      '是否听到对方真实诉求或异议，并围绕当前场景回应，而不是套用泛泛话术。',
      'The learner listens to the counterpart, responds to the actual objection or need, and avoids generic scripts.',
    ],
  },
  credibility: {
    name: ['可信度', 'Credibility'],
    description: [
      '观点是否有证据、案例、限制条件或可信的落地计划支撑。',
      'Claims are supported by evidence, examples, limitations, or a believable implementation plan.',
    ],
  },
  differentiation: {
    name: ['差异化', 'Differentiation'],
    description: [
      '回答是否形成清晰观点、有用对比或差异化价值，而不是听起来可以互换。',
      'The answer creates a clear point of view, useful contrast, or differentiated value instead of sounding interchangeable.',
    ],
  },
}

const DEFAULT_WEIGHTS_BY_CATEGORY: Record<ScenarioTrainingCategory, Record<string, number>> = {
  interview: {
    substance: 30,
    structure: 20,
    relevance: 20,
    credibility: 15,
    differentiation: 15,
  },
  sales: {
    substance: 25,
    structure: 15,
    relevance: 25,
    credibility: 20,
    differentiation: 15,
  },
  negotiation: {
    substance: 25,
    structure: 20,
    relevance: 20,
    credibility: 20,
    differentiation: 15,
  },
  customer_service: {
    substance: 25,
    structure: 20,
    relevance: 25,
    credibility: 20,
    differentiation: 10,
  },
  workplace: {
    substance: 30,
    structure: 25,
    relevance: 20,
    credibility: 15,
    differentiation: 10,
  },
}

const categoryValues: ScenarioTrainingCategory[] = ['sales', 'customer_service', 'negotiation', 'interview', 'workplace']
const difficultyValues: ScenarioTrainingDifficulty[] = ['easy', 'medium', 'hard', 'expert']
const frameworkValues: ScenarioConfigFramework[] = ['prep', 'star', 'scqa', 'pyramid']

function nowIso(): string {
  return new Date().toISOString()
}

function hasObjectShape(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function coerceString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function coerceBoolean(value: unknown, fallback = false): boolean {
  return typeof value === 'boolean' ? value : fallback
}

function coerceCategory(value: unknown, fallback: ScenarioTrainingCategory): ScenarioTrainingCategory {
  return categoryValues.includes(value as ScenarioTrainingCategory) ? value as ScenarioTrainingCategory : fallback
}

function coerceDifficulty(value: unknown, fallback: ScenarioTrainingDifficulty): ScenarioTrainingDifficulty {
  return difficultyValues.includes(value as ScenarioTrainingDifficulty) ? value as ScenarioTrainingDifficulty : fallback
}

function coerceFramework(value: unknown, fallback: ScenarioConfigFramework): ScenarioConfigFramework {
  return frameworkValues.includes(value as ScenarioConfigFramework) ? value as ScenarioConfigFramework : fallback
}

export function normalizeScenarioWeight(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number.parseInt(String(value ?? ''), 10)
  if (!Number.isFinite(parsed)) return 0
  return Math.max(0, Math.min(100, Math.round(parsed)))
}

export function calculateScenarioWeightTotal(weights: ScenarioDimensionWeight[]): number {
  return weights.reduce((total, item) => total + normalizeScenarioWeight(item.weight), 0)
}

export function validateScenarioWeightTotal(weights: ScenarioDimensionWeight[]): ScenarioWeightValidation {
  const selectedCount = weights.length
  const total = calculateScenarioWeightTotal(weights)
  const valid = selectedCount > 0 && total === 100

  if (selectedCount === 0) {
    return {
      total,
      selectedCount,
      valid,
      message: 'Select at least one scoring dimension.',
    }
  }

  if (valid) {
    return {
      total,
      selectedCount,
      valid,
      message: 'Weight total is 100%.',
    }
  }

  return {
    total,
    selectedCount,
    valid,
    message: `Weight total must equal 100%. Current total is ${total}%.`,
  }
}

export function distributeScenarioWeights(dimensionIds: string[]): ScenarioDimensionWeight[] {
  const ids = Array.from(new Set(dimensionIds.map((id) => id.trim()).filter(Boolean)))
  if (ids.length === 0) return []
  const base = Math.floor(100 / ids.length)
  const remainder = 100 - base * ids.length
  return ids.map((dimensionId, index) => ({
    dimensionId,
    weight: base + (index < remainder ? 1 : 0),
  }))
}

function normalizeScenarioWeightTotal(weights: ScenarioDimensionWeight[]): ScenarioDimensionWeight[] {
  const normalized = weights
    .map((item) => ({
      dimensionId: item.dimensionId.trim(),
      weight: normalizeScenarioWeight(item.weight),
    }))
    .filter((item) => item.dimensionId)

  if (normalized.length === 0) return []

  const total = calculateScenarioWeightTotal(normalized)
  if (total === 100) return normalized
  if (total <= 0) return distributeScenarioWeights(normalized.map((item) => item.dimensionId))

  const scaled = normalized.map((item, index) => {
    const raw = (item.weight / total) * 100
    return {
      dimensionId: item.dimensionId,
      fraction: raw - Math.floor(raw),
      index,
      weight: Math.floor(raw),
    }
  })
  let remainder = 100 - scaled.reduce((sum, item) => sum + item.weight, 0)
  const byFraction = [...scaled].sort((a, b) => (
    b.fraction - a.fraction || a.index - b.index
  ))
  for (const item of byFraction) {
    if (remainder <= 0) break
    item.weight += 1
    remainder -= 1
  }

  return scaled.map((item) => ({
    dimensionId: item.dimensionId,
    weight: item.weight,
  }))
}

export function getDefaultDimensionWeights(category: ScenarioTrainingCategory): ScenarioDimensionWeight[] {
  const template = DEFAULT_WEIGHTS_BY_CATEGORY[category] ?? DEFAULT_WEIGHTS_BY_CATEGORY.interview
  return DEFAULT_SCENARIO_DIMENSIONS.map((dimension) => ({
    dimensionId: dimension.id,
    weight: template[dimension.id] ?? 0,
  }))
}

function normalizeDimensionWeights(
  value: unknown,
  fallbackCategory: ScenarioTrainingCategory,
): ScenarioDimensionWeight[] {
  if (!Array.isArray(value)) return getDefaultDimensionWeights(fallbackCategory)

  const byId = new Map<string, ScenarioDimensionWeight>()
  value.forEach((item) => {
    if (!hasObjectShape(item)) return
    const dimensionId = coerceString(item.dimensionId).trim()
    if (!dimensionId) return
    byId.set(dimensionId, {
      dimensionId,
      weight: normalizeScenarioWeight(item.weight),
    })
  })

  const normalized = Array.from(byId.values())
  return normalized.length > 0 ? normalized : getDefaultDimensionWeights(fallbackCategory)
}

function normalizeTrainingPoints(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => coerceString(item).trim()).filter(Boolean)
}

function normalizePersona(value: unknown): ScenarioConfigDraft['persona'] {
  const persona = hasObjectShape(value) ? value : {}
  return {
    name: coerceString(persona.name),
    role: coerceString(persona.role),
    style: coerceString(persona.style),
  }
}

export function buildScenarioDraftFromCard(card: ScenarioTrainingCard): ScenarioConfigDraft {
  return {
    id: card.id,
    title: card.title,
    description: card.description,
    customerProfile: card.customerProfile,
    difficulty: card.difficulty,
    category: card.category,
    required: card.required,
    enabled: true,
    openingLine: card.openingLine,
    persona: {
      name: card.persona.name,
      role: card.persona.role,
      style: card.persona.style,
    },
    learnerRole: card.learnerRole,
    framework: card.framework,
    trainingPoints: [...card.trainingPoints],
    dimensionWeights: getDefaultDimensionWeights(card.category),
    sourceScenarioId: card.id,
    updatedAt: nowIso(),
  }
}

export function createBlankScenarioDraft(partial: Partial<ScenarioConfigDraft> = {}): ScenarioConfigDraft {
  const category = partial.category ?? 'sales'
  return normalizeScenarioDraft({
    id: partial.id ?? `local-scenario-${Date.now().toString(36)}`,
    title: partial.title ?? 'Untitled scenario',
    description: partial.description ?? '',
    customerProfile: partial.customerProfile ?? '',
    difficulty: partial.difficulty ?? 'medium',
    category,
    required: partial.required ?? false,
    enabled: partial.enabled ?? true,
    openingLine: partial.openingLine ?? '',
    persona: partial.persona ?? {
      name: '',
      role: '',
      style: '',
    },
    learnerRole: partial.learnerRole ?? 'Salesperson',
    framework: partial.framework ?? 'prep',
    trainingPoints: partial.trainingPoints ?? [],
    dimensionWeights: partial.dimensionWeights ?? getDefaultDimensionWeights(category),
    sourceScenarioId: partial.sourceScenarioId,
    updatedAt: partial.updatedAt ?? nowIso(),
  })
}

export function normalizeScenarioDraft(value: unknown): ScenarioConfigDraft {
  const source = hasObjectShape(value) ? value : {}
  const category = coerceCategory(source.category, 'sales')
  return {
    id: coerceString(source.id, `local-scenario-${Date.now().toString(36)}`).trim(),
    title: coerceString(source.title, 'Untitled scenario').trim(),
    description: coerceString(source.description).trim(),
    customerProfile: coerceString(source.customerProfile).trim(),
    difficulty: coerceDifficulty(source.difficulty, 'medium'),
    category,
    required: coerceBoolean(source.required, false),
    enabled: coerceBoolean(source.enabled, true),
    openingLine: coerceString(source.openingLine).trim(),
    persona: normalizePersona(source.persona),
    learnerRole: coerceString(source.learnerRole, 'Salesperson').trim(),
    framework: coerceFramework(source.framework, 'prep'),
    trainingPoints: normalizeTrainingPoints(source.trainingPoints),
    dimensionWeights: normalizeDimensionWeights(source.dimensionWeights, category),
    sourceScenarioId: coerceString(source.sourceScenarioId).trim() || undefined,
    updatedAt: coerceString(source.updatedAt, nowIso()),
  }
}

function normalizeDimensionDefinition(value: unknown): ScenarioDimensionDefinition | null {
  if (!hasObjectShape(value)) return null
  const id = coerceString(value.id).trim()
  const name = coerceString(value.name).trim()
  if (!id || !name) return null
  return {
    id,
    name,
    description: coerceString(value.description).trim(),
    enabled: coerceBoolean(value.enabled, true),
    source: value.source === 'local' ? 'local' : 'default',
    updatedAt: coerceString(value.updatedAt, nowIso()),
  }
}

function normalizeDimensions(value: unknown): ScenarioDimensionDefinition[] {
  const byId = new Map<string, ScenarioDimensionDefinition>(
    DEFAULT_SCENARIO_DIMENSIONS.map((dimension) => [dimension.id, { ...dimension }]),
  )

  if (Array.isArray(value)) {
    value.forEach((item) => {
      const normalized = normalizeDimensionDefinition(item)
      if (!normalized) return
      byId.set(normalized.id, {
        ...(byId.get(normalized.id) ?? {}),
        ...normalized,
      })
    })
  }

  return Array.from(byId.values())
}

function normalizeScenarios(value: unknown, fallbackCatalog: ScenarioTrainingCard[]): ScenarioConfigDraft[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeScenarioDraft(item))
      .filter((scenario) => Boolean(scenario.id))
  }
  return fallbackCatalog.map(buildScenarioDraftFromCard)
}

export function createScenarioConfigState(
  catalog: ScenarioTrainingCard[] = [],
): ScenarioConfigState {
  const scenarios = catalog.map(buildScenarioDraftFromCard)
  return {
    version: 1,
    dimensions: DEFAULT_SCENARIO_DIMENSIONS.map((dimension) => ({ ...dimension })),
    scenarios,
    selectedScenarioId: scenarios[0]?.id,
    selectedDimensionId: DEFAULT_SCENARIO_DIMENSIONS[0]?.id,
    updatedAt: nowIso(),
  }
}

export function normalizeScenarioConfigState(
  value: unknown,
  fallbackCatalog: ScenarioTrainingCard[] = [],
): ScenarioConfigState {
  if (!hasObjectShape(value)) return createScenarioConfigState(fallbackCatalog)

  const dimensions = normalizeDimensions(value.dimensions)
  const scenarios = normalizeScenarios(value.scenarios, fallbackCatalog)
  const selectedScenarioId = coerceString(value.selectedScenarioId).trim()
  const selectedDimensionId = coerceString(value.selectedDimensionId).trim()

  return {
    version: 1,
    dimensions,
    scenarios,
    selectedScenarioId: scenarios.some((scenario) => scenario.id === selectedScenarioId)
      ? selectedScenarioId
      : scenarios[0]?.id,
    selectedDimensionId: dimensions.some((dimension) => dimension.id === selectedDimensionId)
      ? selectedDimensionId
      : dimensions[0]?.id,
    updatedAt: coerceString(value.updatedAt, nowIso()),
  }
}

export function upsertScenarioConfigDraft(
  state: ScenarioConfigState,
  draft: ScenarioConfigDraft,
): ScenarioConfigState {
  const normalized = normalizeScenarioDraft({
    ...draft,
    updatedAt: nowIso(),
  })
  const exists = state.scenarios.some((scenario) => scenario.id === normalized.id)
  const scenarios = exists
    ? state.scenarios.map((scenario) => scenario.id === normalized.id ? normalized : scenario)
    : [normalized, ...state.scenarios]

  return {
    ...state,
    scenarios,
    selectedScenarioId: normalized.id,
    updatedAt: nowIso(),
  }
}

export function upsertScenarioDimension(
  state: ScenarioConfigState,
  dimension: ScenarioDimensionDefinition,
): ScenarioConfigState {
  const normalized = normalizeDimensionDefinition({
    ...dimension,
    source: dimension.source ?? 'local',
    updatedAt: nowIso(),
  })
  if (!normalized) return state

  const exists = state.dimensions.some((item) => item.id === normalized.id)
  const dimensions = exists
    ? state.dimensions.map((item) => item.id === normalized.id ? normalized : item)
    : [normalized, ...state.dimensions]

  return {
    ...state,
    dimensions,
    selectedDimensionId: normalized.id,
    updatedAt: nowIso(),
  }
}

export function removeScenarioConfigDraft(
  state: ScenarioConfigState,
  scenarioId: string,
): ScenarioConfigState {
  const id = scenarioId.trim()
  const removedIndex = state.scenarios.findIndex((scenario) => scenario.id === id)
  if (!id || removedIndex < 0) return state

  const scenarios = state.scenarios.filter((scenario) => scenario.id !== id)
  const selectedScenarioId = state.selectedScenarioId === id
    ? scenarios[Math.min(removedIndex, scenarios.length - 1)]?.id
    : scenarios.some((scenario) => scenario.id === state.selectedScenarioId)
      ? state.selectedScenarioId
      : scenarios[0]?.id

  return {
    ...state,
    scenarios,
    selectedScenarioId,
    updatedAt: nowIso(),
  }
}

export function removeScenarioDimension(
  state: ScenarioConfigState,
  dimensionId: string,
): ScenarioConfigState {
  const id = dimensionId.trim()
  const existing = state.dimensions.find((dimension) => dimension.id === id)
  if (!id || !existing || existing.source !== 'local') return state

  const updatedAt = nowIso()
  const dimensions = state.dimensions.filter((dimension) => dimension.id !== id)
  const scenarios = state.scenarios.map((scenario) => {
    if (!scenario.dimensionWeights.some((item) => item.dimensionId === id)) return scenario

    const remainingWeights = scenario.dimensionWeights.filter((item) => item.dimensionId !== id)
    return {
      ...scenario,
      dimensionWeights: remainingWeights.length > 0
        ? normalizeScenarioWeightTotal(remainingWeights)
        : getDefaultDimensionWeights(scenario.category),
      updatedAt,
    }
  })
  const selectedDimensionId = state.selectedDimensionId === id
    ? dimensions[0]?.id
    : dimensions.some((dimension) => dimension.id === state.selectedDimensionId)
      ? state.selectedDimensionId
      : dimensions[0]?.id

  return {
    ...state,
    dimensions,
    scenarios,
    selectedDimensionId,
    updatedAt,
  }
}

export function loadScenarioConfigState(
  fallbackCatalog: ScenarioTrainingCard[] = [],
): ScenarioConfigState {
  if (typeof window === 'undefined') return createScenarioConfigState(fallbackCatalog)
  try {
    const raw = window.localStorage.getItem(SCENARIO_CONFIG_STORAGE_KEY)
    if (!raw) return createScenarioConfigState(fallbackCatalog)
    return normalizeScenarioConfigState(JSON.parse(raw), fallbackCatalog)
  } catch {
    return createScenarioConfigState(fallbackCatalog)
  }
}

export function saveScenarioConfigState(state: ScenarioConfigState): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(SCENARIO_CONFIG_STORAGE_KEY, JSON.stringify(state))
}
