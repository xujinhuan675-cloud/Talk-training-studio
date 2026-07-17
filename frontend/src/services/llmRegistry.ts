import { getAuthRequestHeaders } from './auth'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface LLMModelMetadata {
  name: string
  provider?: string | null
  endpoint?: string | null
  display_name?: string | null
  is_default?: boolean
  context_window?: number | null
  max_output_tokens?: number | null
  [key: string]: unknown
}

export interface LLMEndpointMetadata {
  provider: string
  endpoint?: string | null
  wire_api?: string | null
  default_model?: string | null
  models: LLMModelMetadata[]
  [key: string]: unknown
}

export interface LLMProviderMetadata {
  provider: string
  default_model?: string | null
  endpoint?: string | null
  wire_api?: string | null
  max_retries?: number | null
  models: LLMModelMetadata[]
  endpoints: LLMEndpointMetadata[]
  [key: string]: unknown
}

export interface LLMModelChoice {
  key: string
  provider: string
  providerLabel: string
  model: string
  modelLabel: string
  endpoint: string | null
  wireApi: string | null
  isDefault: boolean
  metadata: LLMModelMetadata
}

export const LLM_REGISTRY_API = '/api/v1/training-studio/llm-registry'

function hasObjectShape(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function unwrapApiResponse<T>(value: ApiResponse<T> | T): T {
  if (hasObjectShape(value) && 'data' in value) {
    return value.data as T
  }
  return value as T
}

function cleanText(value: unknown): string | null {
  if (value === undefined || value === null) return null
  const text = String(value).trim()
  return text || null
}

async function readError(resp: Response, fallback: string): Promise<Error> {
  const json = await resp.json().catch(() => null)
  const detail = typeof json?.detail === 'string' ? json.detail : json?.detail?.message
  return new Error(json?.error?.details || detail || json?.message || `${fallback}: ${resp.status}`)
}

export async function fetchLlmRegistry(): Promise<LLMProviderMetadata> {
  const resp = await fetch(LLM_REGISTRY_API, {
    headers: getAuthRequestHeaders(),
  })
  if (!resp.ok) {
    throw await readError(resp, 'Failed to fetch LLM registry')
  }
  const registry = unwrapApiResponse<LLMProviderMetadata>(await resp.json())
  return {
    ...registry,
    models: Array.isArray(registry.models) ? registry.models : [],
    endpoints: Array.isArray(registry.endpoints) ? registry.endpoints : [],
  }
}

export function getLlmRegistryModelChoices(registry: LLMProviderMetadata | null | undefined): LLMModelChoice[] {
  if (!registry) return []

  const choices: LLMModelChoice[] = []
  const seen = new Set<string>()
  const appendChoice = (
    model: LLMModelMetadata,
    fallback: {
      provider?: string | null
      endpoint?: string | null
      wireApi?: string | null
      defaultModel?: string | null
    },
  ) => {
    const modelName = cleanText(model.name)
    const provider = cleanText(model.provider) ?? cleanText(fallback.provider) ?? cleanText(registry.provider)
    if (!modelName || !provider) return

    const endpoint = cleanText(model.endpoint) ?? cleanText(fallback.endpoint)
    const wireApi = cleanText(model.wire_api) ?? cleanText(fallback.wireApi)
    const key = [provider, endpoint ?? '', modelName].join('::')
    if (seen.has(key)) return
    seen.add(key)

    choices.push({
      key,
      provider,
      providerLabel: provider,
      model: modelName,
      modelLabel: cleanText(model.display_name) ?? modelName,
      endpoint,
      wireApi,
      isDefault: Boolean(model.is_default || fallback.defaultModel === modelName || registry.default_model === modelName),
      metadata: model,
    })
  }

  for (const endpoint of registry.endpoints || []) {
    for (const model of endpoint.models || []) {
      appendChoice(model, {
        provider: endpoint.provider,
        endpoint: endpoint.endpoint,
        wireApi: endpoint.wire_api,
        defaultModel: endpoint.default_model,
      })
    }
  }

  for (const model of registry.models || []) {
    appendChoice(model, {
      provider: registry.provider,
      endpoint: registry.endpoint,
      wireApi: registry.wire_api,
      defaultModel: registry.default_model,
    })
  }

  return choices
}

export function selectDefaultLlmModelChoice(
  registry: LLMProviderMetadata | null | undefined,
): LLMModelChoice | null {
  const choices = getLlmRegistryModelChoices(registry)
  return choices.find((choice) => choice.isDefault) ?? choices[0] ?? null
}
