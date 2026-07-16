import type { ScenarioTrainingCard } from '../data/trainingScenarios'
import {
  normalizeScenarioConfigState,
  type ScenarioConfigState,
} from '../data/scenarioConfig'
import { getAuthRequestHeaders } from './auth'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface ScenarioConfigDocumentDTO {
  scenarios?: unknown
  dimensions?: unknown
  selectedScenarioId?: string | null
  selectedDimensionId?: string | null
  updated_at?: string | null
  updatedAt?: string | null
}

const SCENARIO_CONFIG_API = '/api/v1/training-studio/scenario-config'

function hasObjectShape(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function unwrapApiResponse<T>(value: ApiResponse<T> | T): T {
  if (hasObjectShape(value) && 'data' in value && hasObjectShape(value.data)) {
    return value.data as T
  }
  return value as T
}

function toScenarioConfigState(
  dto: ScenarioConfigDocumentDTO,
  fallbackCatalog: ScenarioTrainingCard[],
  currentState?: ScenarioConfigState,
): ScenarioConfigState {
  return normalizeScenarioConfigState(
    {
      scenarios: dto.scenarios,
      dimensions: dto.dimensions,
      selectedScenarioId: dto.selectedScenarioId ?? currentState?.selectedScenarioId,
      selectedDimensionId: dto.selectedDimensionId ?? currentState?.selectedDimensionId,
      updatedAt: dto.updated_at ?? dto.updatedAt ?? currentState?.updatedAt,
    },
    fallbackCatalog,
  )
}

function toScenarioConfigDocument(state: ScenarioConfigState): ScenarioConfigDocumentDTO {
  return {
    scenarios: state.scenarios,
    dimensions: state.dimensions,
    selectedScenarioId: state.selectedScenarioId,
    selectedDimensionId: state.selectedDimensionId,
    updated_at: state.updatedAt,
  }
}

async function readError(resp: Response, fallback: string): Promise<Error> {
  if ([502, 503, 504].includes(resp.status)) {
    return new Error(`${fallback}: backend service unavailable`)
  }
  const json = await resp.json().catch(() => null)
  const detail = typeof json?.detail === 'string' ? json.detail : json?.detail?.message
  return new Error(json?.error?.details || detail || json?.message || `${fallback}: ${resp.status}`)
}

async function requestScenarioConfig<T>(init?: RequestInit, errorMessage = 'Scenario config request failed'): Promise<T> {
  const resp = await fetch(SCENARIO_CONFIG_API, {
    ...init,
    headers: {
      ...getAuthRequestHeaders(),
      ...(init?.headers as Record<string, string> | undefined),
    },
  })
  if (!resp.ok) {
    throw await readError(resp, errorMessage)
  }
  return unwrapApiResponse<T>(await resp.json())
}

export async function fetchScenarioConfig(
  fallbackCatalog: ScenarioTrainingCard[] = [],
  currentState?: ScenarioConfigState,
): Promise<ScenarioConfigState> {
  const dto = await requestScenarioConfig<ScenarioConfigDocumentDTO>(
    undefined,
    'Failed to fetch scenario config',
  )
  return toScenarioConfigState(dto, fallbackCatalog, currentState)
}

export async function saveScenarioConfig(
  state: ScenarioConfigState,
  fallbackCatalog: ScenarioTrainingCard[] = [],
): Promise<ScenarioConfigState> {
  const dto = await requestScenarioConfig<ScenarioConfigDocumentDTO>(
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(toScenarioConfigDocument(state)),
    },
    'Failed to save scenario config',
  )
  return toScenarioConfigState(dto, fallbackCatalog, state)
}
