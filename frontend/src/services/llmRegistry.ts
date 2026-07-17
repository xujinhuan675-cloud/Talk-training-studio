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

export type LLMModelSpecsField = LLMModelSpecMetadata[] | Record<string, unknown>
export type LLMEndpointsConfigField = LLMEndpointConfigMetadata[] | Record<string, unknown>

export interface LLMModelSpecMetadata {
  name?: string | null
  label?: string | null
  description?: string | null
  preset?: Record<string, unknown> | null
  capabilities?: unknown
  context_window?: number | null
  max_output_tokens?: number | null
  disabled?: boolean
  selectable?: boolean
  [key: string]: unknown
}

export interface LLMEndpointConfigMetadata {
  provider?: string | null
  endpoint?: string | null
  name?: string | null
  label?: string | null
  title?: string | null
  wire_api?: string | null
  default_model?: string | null
  models?: unknown
  disabled?: boolean
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
  model_specs?: LLMModelSpecsField | null
  endpoints_config?: LLMEndpointsConfigField | null
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
  disabled: boolean
  disabledReason: string | null
  description: string | null
  capabilities: string[]
  contextWindow: number | null
  maxOutputTokens: number | null
  metadata: LLMModelMetadata
  modelSpec: LLMModelSpecMetadata | null
  endpointConfig: LLMEndpointConfigMetadata | null
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

function cleanNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, Math.round(value))
  }
  if (typeof value === 'string') {
    const parsed = Number(value.replace(/[, _]/g, '').trim())
    return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : null
  }
  return null
}

function cleanBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function getRecordValue(source: unknown, keys: string[]): unknown {
  const record = hasObjectShape(source) ? source : null
  if (!record) return undefined
  for (const key of keys) {
    if (key in record) return record[key]
  }
  return undefined
}

function getRecordText(source: unknown, keys: string[]): string | null {
  return cleanText(getRecordValue(source, keys))
}

function getRecordNumber(source: unknown, keys: string[]): number | null {
  for (const key of keys) {
    const value = getRecordValue(source, [key])
    const direct = cleanNumber(value)
    if (direct !== null) return direct
    if (hasObjectShape(value)) {
      const nested = getRecordNumber(value, ['window', 'tokens', 'max', 'max_tokens', 'maxTokens'])
      if (nested !== null) return nested
    }
  }
  return null
}

function getRecordBoolean(source: unknown, keys: string[]): boolean | null {
  for (const key of keys) {
    const value = cleanBoolean(getRecordValue(source, [key]))
    if (value !== null) return value
  }
  return null
}

function normalizeCapabilityList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return Array.from(new Set(value.map(cleanText).filter((item): item is string => Boolean(item))))
  }
  if (typeof value === 'string') {
    return Array.from(new Set(value.split(/[,/|]/).map(cleanText).filter((item): item is string => Boolean(item))))
  }
  if (hasObjectShape(value)) {
    return Object.entries(value)
      .filter(([, enabled]) => enabled === true)
      .map(([key]) => key)
  }
  return []
}

function looksLikeUrl(value: string | null): boolean {
  return Boolean(value && /^[a-z][a-z\d+.-]*:\/\//i.test(value))
}

function toModelMetadata(value: unknown, fallbackName?: string | null): LLMModelMetadata | null {
  if (typeof value === 'string') {
    const name = cleanText(value)
    return name ? { name } : null
  }
  if (!hasObjectShape(value)) return null
  const name = cleanText(value.name) ?? cleanText(value.model) ?? cleanText(fallbackName)
  return name ? { ...value, name } as LLMModelMetadata : null
}

function normalizeModelSpecs(value: unknown): LLMModelSpecMetadata[] {
  const normalize = (entry: unknown, fallbackName?: string): LLMModelSpecMetadata | null => {
    if (typeof entry === 'string') {
      const name = cleanText(entry)
      return name ? { name } : null
    }
    if (!hasObjectShape(entry)) return null
    return {
      ...entry,
      name: cleanText(entry.name) ?? cleanText(fallbackName),
    } as LLMModelSpecMetadata
  }

  const collect = (entries: unknown[]): LLMModelSpecMetadata[] => (
    entries.map((entry) => normalize(entry)).filter((entry): entry is LLMModelSpecMetadata => Boolean(entry))
  )

  if (Array.isArray(value)) return collect(value)
  if (!hasObjectShape(value)) return []

  for (const key of ['list', 'specs', 'model_specs', 'modelSpecs']) {
    const list = value[key]
    if (Array.isArray(list)) return collect(list)
  }

  return Object.entries(value)
    .map(([name, entry]) => normalize(entry, name))
    .filter((entry): entry is LLMModelSpecMetadata => Boolean(entry))
}

function normalizeEndpointConfigs(value: unknown): LLMEndpointConfigMetadata[] {
  const normalize = (entry: unknown, fallbackProvider?: string): LLMEndpointConfigMetadata | null => {
    if (!hasObjectShape(entry)) return null
    return {
      ...entry,
      provider: cleanText(entry.provider) ?? cleanText(fallbackProvider),
    } as LLMEndpointConfigMetadata
  }

  if (Array.isArray(value)) {
    return value.map((entry) => normalize(entry)).filter((entry): entry is LLMEndpointConfigMetadata => Boolean(entry))
  }
  if (!hasObjectShape(value)) return []

  return Object.entries(value).flatMap(([provider, entry]) => {
    if (Array.isArray(entry)) {
      return entry
        .map((item) => normalize(item, provider))
        .filter((item): item is LLMEndpointConfigMetadata => Boolean(item))
    }
    const normalized = normalize(entry, provider)
    return normalized ? [normalized] : []
  })
}

function normalizeEndpointConfigModels(config: LLMEndpointConfigMetadata): LLMModelMetadata[] {
  const value = config.models
  if (Array.isArray(value)) {
    return value.map((item) => toModelMetadata(item)).filter((item): item is LLMModelMetadata => Boolean(item))
  }
  if (!hasObjectShape(value)) return []

  for (const key of ['default', 'defaults', 'list', 'available', 'supported']) {
    const list = value[key]
    if (Array.isArray(list)) {
      return list.map((item) => toModelMetadata(item)).filter((item): item is LLMModelMetadata => Boolean(item))
    }
  }

  return Object.entries(value)
    .map(([name, entry]) => toModelMetadata(entry, name))
    .filter((entry): entry is LLMModelMetadata => Boolean(entry))
}

function getEndpointConfigProvider(config: LLMEndpointConfigMetadata): string | null {
  const explicit = getRecordText(config, ['provider', 'name', 'key'])
  if (explicit) return explicit
  const endpoint = getRecordText(config, ['endpoint'])
  return looksLikeUrl(endpoint) ? null : endpoint
}

function getEndpointConfigEndpoint(config: LLMEndpointConfigMetadata): string | null {
  const explicit = getRecordText(config, ['endpoint_url', 'endpointUrl', 'base_url', 'baseURL', 'baseUrl', 'url'])
  if (explicit) return explicit
  const endpoint = getRecordText(config, ['endpoint'])
  return looksLikeUrl(endpoint) ? endpoint : null
}

function getEndpointConfigLabel(config: LLMEndpointConfigMetadata | null): string | null {
  return getRecordText(config, ['label', 'title', 'display_name', 'displayName'])
}

function getEndpointConfigDefaultModel(config: LLMEndpointConfigMetadata | null): string | null {
  if (!config) return null
  const direct = getRecordText(config, ['default_model', 'defaultModel'])
  if (direct) return direct
  const models = hasObjectShape(config.models) ? config.models : null
  if (!models) return null
  const defaults = models.default ?? models.defaults
  if (Array.isArray(defaults)) return cleanText(defaults[0])
  return cleanText(defaults)
}

function findEndpointConfig(
  configs: LLMEndpointConfigMetadata[],
  provider: string,
  endpoint: string | null,
): LLMEndpointConfigMetadata | null {
  const normalizedProvider = provider.toLowerCase()
  return configs.find((config) => {
    const configProvider = getEndpointConfigProvider(config)
    const configEndpoint = getEndpointConfigEndpoint(config)
    const providerMatches = !configProvider || configProvider.toLowerCase() === normalizedProvider
    const endpointMatches = !configEndpoint || !endpoint || configEndpoint === endpoint
    return providerMatches && endpointMatches
  }) ?? null
}

function getSpecPreset(spec: LLMModelSpecMetadata | null): Record<string, unknown> | null {
  return hasObjectShape(spec?.preset) ? spec.preset : null
}

function getSpecModelName(spec: LLMModelSpecMetadata | null): string | null {
  const preset = getSpecPreset(spec)
  return getRecordText(preset, ['model', 'model_name', 'modelName'])
    ?? getRecordText(spec, ['model', 'name'])
}

function getSpecProvider(spec: LLMModelSpecMetadata | null): string | null {
  const preset = getSpecPreset(spec)
  return getRecordText(preset, ['provider', 'endpoint', 'endpointType', 'endpoint_type'])
    ?? getRecordText(spec, ['provider', 'endpoint'])
}

function getSpecEndpoint(spec: LLMModelSpecMetadata | null): string | null {
  const preset = getSpecPreset(spec)
  return getRecordText(preset, ['endpoint_url', 'endpointUrl', 'base_url', 'baseURL', 'baseUrl', 'url'])
    ?? getRecordText(spec, ['endpoint_url', 'endpointUrl', 'base_url', 'baseURL', 'baseUrl', 'url'])
    ?? (looksLikeUrl(getRecordText(spec, ['endpoint'])) ? getRecordText(spec, ['endpoint']) : null)
}

function getSpecWireApi(spec: LLMModelSpecMetadata | null): string | null {
  const preset = getSpecPreset(spec)
  return getRecordText(preset, ['wire_api', 'wireApi'])
    ?? getRecordText(spec, ['wire_api', 'wireApi'])
}

function modelSpecMatchesChoice(
  spec: LLMModelSpecMetadata,
  modelName: string,
  provider: string,
  endpoint: string | null,
  wireApi: string | null,
): boolean {
  const specNames = [
    getSpecModelName(spec),
    getRecordText(spec, ['name']),
    getRecordText(spec, ['model']),
  ].filter((value): value is string => Boolean(value))

  if (specNames.length === 0) return false
  if (specNames.length > 0 && !specNames.some((name) => name === modelName)) return false

  const specProvider = getSpecProvider(spec)
  if (specProvider && specProvider.toLowerCase() !== provider.toLowerCase() && specProvider !== endpoint) {
    return false
  }

  const specEndpoint = getSpecEndpoint(spec)
  if (specEndpoint && endpoint && specEndpoint !== endpoint) return false

  const specWireApi = getSpecWireApi(spec)
  if (specWireApi && wireApi && specWireApi !== wireApi) return false

  return true
}

function findModelSpec(
  specs: LLMModelSpecMetadata[],
  modelName: string,
  provider: string,
  endpoint: string | null,
  wireApi: string | null = null,
): LLMModelSpecMetadata | null {
  return specs.find((spec) => modelSpecMatchesChoice(spec, modelName, provider, endpoint, wireApi)) ?? null
}

function getSpecContextWindow(spec: LLMModelSpecMetadata | null): number | null {
  const preset = getSpecPreset(spec)
  return getRecordNumber(spec, ['context_window', 'contextWindow', 'context', 'max_context_tokens', 'maxContextTokens'])
    ?? getRecordNumber(preset, ['context_window', 'contextWindow', 'context', 'max_context_tokens', 'maxContextTokens'])
}

function getModelContextWindow(model: LLMModelMetadata): number | null {
  return getRecordNumber(model, ['context_window', 'contextWindow', 'context', 'max_context_tokens', 'maxContextTokens'])
}

function getSpecMaxOutputTokens(spec: LLMModelSpecMetadata | null): number | null {
  const preset = getSpecPreset(spec)
  return getRecordNumber(spec, ['max_output_tokens', 'maxOutputTokens', 'max_output', 'maxOutput'])
    ?? getRecordNumber(preset, ['max_output_tokens', 'maxOutputTokens', 'max_output', 'maxOutput', 'max_tokens', 'maxTokens'])
}

function getModelMaxOutputTokens(model: LLMModelMetadata): number | null {
  return getRecordNumber(model, ['max_output_tokens', 'maxOutputTokens', 'max_output', 'maxOutput', 'max_tokens', 'maxTokens'])
}

function isDisabledByMetadata(...items: Array<Record<string, unknown> | null | undefined>): boolean {
  return items.some((item) => (
    getRecordBoolean(item, ['disabled', 'unavailable', 'unselectable']) === true
    || getRecordBoolean(item, ['enabled', 'available', 'selectable']) === false
  ))
}

function isHiddenByMetadata(...items: Array<Record<string, unknown> | null | undefined>): boolean {
  return items.some((item) => (
    getRecordBoolean(item, ['hidden', 'hide_in_menu', 'hideInMenu']) === true
    || getRecordBoolean(item, ['show_in_menu', 'showInMenu']) === false
  ))
}

function getDisabledReason(...items: Array<Record<string, unknown> | null | undefined>): string | null {
  for (const item of items) {
    const reason = getRecordText(item, ['disabled_reason', 'disabledReason', 'unavailable_reason', 'unavailableReason'])
    if (reason) return reason
  }
  return null
}

export function isLlmModelChoiceSelectable(choice: LLMModelChoice | null | undefined): choice is LLMModelChoice {
  return Boolean(choice && !choice.disabled)
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
  const seenBaseKeys = new Set<string>()
  const modelSpecs = normalizeModelSpecs(registry.model_specs)
  const endpointConfigs = normalizeEndpointConfigs(registry.endpoints_config)
  const appendChoice = (
    model: LLMModelMetadata,
    fallback: {
      provider?: string | null
      endpoint?: string | null
      wireApi?: string | null
      defaultModel?: string | null
    },
    preferredSpec?: LLMModelSpecMetadata | null,
    preferredEndpointConfig?: LLMEndpointConfigMetadata | null,
  ) => {
    const modelName = cleanText(model.name)
    const provider = cleanText(model.provider) ?? cleanText(fallback.provider) ?? cleanText(registry.provider)
    if (!modelName || !provider) return

    const endpoint = cleanText(model.endpoint) ?? cleanText(fallback.endpoint)
    const endpointConfig = preferredEndpointConfig ?? findEndpointConfig(endpointConfigs, provider, endpoint)
    const fallbackWireApi = cleanText(model.wire_api)
      ?? cleanText(fallback.wireApi)
      ?? getRecordText(endpointConfig, ['wire_api', 'wireApi'])
    const modelSpec = preferredSpec ?? findModelSpec(modelSpecs, modelName, provider, endpoint, fallbackWireApi)
    const specPreset = getSpecPreset(modelSpec)
    const defaultModel = cleanText(fallback.defaultModel)
      ?? getEndpointConfigDefaultModel(endpointConfig)
      ?? cleanText(registry.default_model)
    const wireApi = fallbackWireApi ?? getSpecWireApi(modelSpec) ?? getRecordText(specPreset, ['wire_api', 'wireApi'])
    if (isHiddenByMetadata(endpointConfig, model, modelSpec)) return

    const key = [provider, endpoint ?? '', wireApi ?? '', modelName].join('::')
    const baseKey = [provider, endpoint ?? '', modelName].join('::')
    if (!wireApi && seenBaseKeys.has(baseKey)) return
    if (seen.has(key)) return
    seen.add(key)
    seenBaseKeys.add(baseKey)

    const specCapabilities = normalizeCapabilityList(modelSpec?.capabilities)
    const modelCapabilities = normalizeCapabilityList(model.capabilities)
    const contextWindow = getSpecContextWindow(modelSpec) ?? getModelContextWindow(model)
    const maxOutputTokens = getSpecMaxOutputTokens(modelSpec) ?? getModelMaxOutputTokens(model)
    const disabled = isDisabledByMetadata(endpointConfig, model, modelSpec)

    choices.push({
      key,
      provider,
      providerLabel: getRecordText(model, ['provider_label', 'providerLabel'])
        ?? getEndpointConfigLabel(endpointConfig)
        ?? provider,
      model: modelName,
      modelLabel: getRecordText(modelSpec, ['label', 'display_name', 'displayName'])
        ?? getRecordText(specPreset, ['modelLabel', 'model_label', 'label'])
        ?? cleanText(model.display_name)
        ?? modelName,
      endpoint,
      wireApi,
      isDefault: Boolean(model.is_default || defaultModel === modelName),
      disabled,
      disabledReason: getDisabledReason(modelSpec, model, endpointConfig),
      description: getRecordText(modelSpec, ['description'])
        ?? getRecordText(model, ['description']),
      capabilities: specCapabilities.length > 0 ? specCapabilities : modelCapabilities,
      contextWindow,
      maxOutputTokens,
      metadata: model,
      modelSpec,
      endpointConfig,
    })
  }

  for (const endpoint of registry.endpoints || []) {
    const endpointConfig = findEndpointConfig(endpointConfigs, endpoint.provider, cleanText(endpoint.endpoint))
    for (const model of endpoint.models || []) {
      appendChoice(model, {
        provider: endpoint.provider,
        endpoint: endpoint.endpoint,
        wireApi: endpoint.wire_api,
        defaultModel: endpoint.default_model,
      }, null, endpointConfig)
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

  for (const endpointConfig of endpointConfigs) {
    const provider = getEndpointConfigProvider(endpointConfig) ?? cleanText(registry.provider)
    if (!provider) continue
    const endpoint = getEndpointConfigEndpoint(endpointConfig)
    for (const model of normalizeEndpointConfigModels(endpointConfig)) {
      appendChoice({
        ...model,
        provider: cleanText(model.provider) ?? provider,
        endpoint: cleanText(model.endpoint) ?? endpoint,
      }, {
        provider,
        endpoint,
        wireApi: getRecordText(endpointConfig, ['wire_api', 'wireApi']),
        defaultModel: getEndpointConfigDefaultModel(endpointConfig),
      }, null, endpointConfig)
    }
  }

  for (const modelSpec of modelSpecs) {
    const modelName = getSpecModelName(modelSpec)
    if (!modelName) continue
    const specPreset = getSpecPreset(modelSpec)
    const provider = getSpecProvider(modelSpec) ?? cleanText(registry.provider)
    if (!provider) continue
    const endpoint = getSpecEndpoint(modelSpec)
    appendChoice({
      name: modelName,
      provider,
      endpoint,
      display_name: getRecordText(modelSpec, ['label', 'display_name', 'displayName']) ?? undefined,
    }, {
      provider,
      endpoint,
      wireApi: getRecordText(specPreset, ['wire_api', 'wireApi']),
      defaultModel: cleanText(registry.default_model),
    }, modelSpec)
  }

  return choices
}

export function selectDefaultLlmModelChoice(
  registry: LLMProviderMetadata | null | undefined,
): LLMModelChoice | null {
  const choices = getLlmRegistryModelChoices(registry)
  return choices.find((choice) => choice.isDefault && isLlmModelChoiceSelectable(choice))
    ?? choices.find(isLlmModelChoiceSelectable)
    ?? null
}
