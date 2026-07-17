import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadLlmRegistryModule() {
  const sourcePath = path.resolve('src/services/llmRegistry.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
    .replace(
      "import { getAuthRequestHeaders } from './auth'\n",
      "function getAuthRequestHeaders() { return { 'X-Mock-User': 'admin' } }\n",
    )
  const outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(
    os.tmpdir(),
    `llm-registry-${process.pid}-${Date.now()}.mjs`,
  )
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const llmRegistry = await loadLlmRegistryModule()

const registryPayload = {
  provider: 'talkwise',
  default_model: 'gpt-registry',
  models: [
    {
      name: 'gpt-registry',
      provider: 'openai',
      endpoint: 'https://openai.example/v1',
      is_default: true,
    },
    {
      name: 'claude-registry',
      provider: 'anthropic',
      endpoint: 'https://anthropic.example',
    },
  ],
  endpoints: [
    {
      provider: 'openai',
      endpoint: 'https://openai.example/v1',
      wire_api: 'responses',
      default_model: 'gpt-registry',
      models: [
        {
          name: 'gpt-registry',
          provider: 'openai',
          endpoint: 'https://openai.example/v1',
          display_name: 'GPT Registry',
        },
      ],
    },
    {
      provider: 'anthropic',
      endpoint: 'https://anthropic.example',
      wire_api: 'messages',
      default_model: 'claude-registry',
      models: [
        {
          name: 'claude-registry',
          display_name: 'Claude Registry',
        },
      ],
    },
  ],
}

test('getLlmRegistryModelChoices flattens endpoint models and de-duplicates registry models', () => {
  const choices = llmRegistry.getLlmRegistryModelChoices(registryPayload)

  assert.deepEqual(
    choices.map((choice) => ({
      provider: choice.provider,
      model: choice.model,
      label: choice.modelLabel,
      wireApi: choice.wireApi,
      isDefault: choice.isDefault,
    })),
    [
      {
        provider: 'openai',
        model: 'gpt-registry',
        label: 'GPT Registry',
        wireApi: 'responses',
        isDefault: true,
      },
      {
        provider: 'anthropic',
        model: 'claude-registry',
        label: 'Claude Registry',
        wireApi: 'messages',
        isDefault: true,
      },
    ],
  )
})

test('selectDefaultLlmModelChoice returns the registry default choice', () => {
  const choice = llmRegistry.selectDefaultLlmModelChoice(registryPayload)

  assert.equal(choice.provider, 'openai')
  assert.equal(choice.model, 'gpt-registry')
})

test('getLlmRegistryModelChoices merges model specs and endpoint config display metadata', () => {
  const choices = llmRegistry.getLlmRegistryModelChoices({
    provider: 'talkwise',
    models: [
      {
        name: 'gpt-4o',
        provider: 'openai',
        display_name: 'Raw GPT-4o',
        context_window: 64000,
        max_output_tokens: 4096,
        capabilities: ['text'],
      },
    ],
    endpoints: [],
    endpoints_config: {
      openai: {
        title: 'OpenAI Compatible',
        wire_api: 'responses',
        default_model: 'gpt-4o',
        models: {
          default: ['gpt-4o', 'gpt-4o-mini'],
        },
      },
    },
    model_specs: [
      {
        name: 'gpt-4o',
        label: 'TalkWise GPT-4o',
        description: 'Best general training model',
        capabilities: ['vision', 'tools'],
        context_window: 128000,
        max_output_tokens: 16384,
        preset: {
          endpoint: 'openai',
          model: 'gpt-4o',
        },
      },
    ],
  })

  const specChoice = choices.find((choice) => choice.model === 'gpt-4o')
  assert.equal(specChoice.modelLabel, 'TalkWise GPT-4o')
  assert.equal(specChoice.description, 'Best general training model')
  assert.deepEqual(specChoice.capabilities, ['vision', 'tools'])
  assert.equal(specChoice.contextWindow, 128000)
  assert.equal(specChoice.maxOutputTokens, 16384)
  assert.equal(specChoice.providerLabel, 'OpenAI Compatible')
  assert.equal(specChoice.wireApi, 'responses')
  assert.equal(specChoice.isDefault, true)

  const configOnlyChoice = choices.find((choice) => choice.model === 'gpt-4o-mini')
  assert.equal(configOnlyChoice.provider, 'openai')
  assert.equal(configOnlyChoice.modelLabel, 'gpt-4o-mini')
})

test('getLlmRegistryModelChoices preserves backend model spec endpoint URLs without duplicates', () => {
  const choices = llmRegistry.getLlmRegistryModelChoices({
    provider: 'talkwise',
    default_model: 'claude-sonnet-test',
    models: [],
    endpoints: [],
    endpoints_config: {
      'anthropic::https://anthropic.example::messages': {
        provider: 'anthropic',
        endpoint: 'https://anthropic.example',
        wire_api: 'messages',
        default_model: 'claude-sonnet-test',
        models: ['claude-sonnet-test'],
      },
    },
    model_specs: [
      {
        name: 'anthropic::https://anthropic.example::messages::claude-sonnet-test',
        label: 'Claude Sonnet Test',
        provider: 'anthropic',
        endpoint: 'https://anthropic.example',
        wire_api: 'messages',
        model: 'claude-sonnet-test',
        selectable: true,
      },
    ],
  })

  assert.equal(choices.length, 1)
  assert.equal(choices[0].provider, 'anthropic')
  assert.equal(choices[0].endpoint, 'https://anthropic.example')
  assert.equal(choices[0].wireApi, 'messages')
  assert.equal(choices[0].model, 'claude-sonnet-test')
  assert.equal(choices[0].modelLabel, 'Claude Sonnet Test')
})

test('getLlmRegistryModelChoices keeps wire API variants distinct and hides hidden specs', () => {
  const choices = llmRegistry.getLlmRegistryModelChoices({
    provider: 'talkwise',
    default_model: 'gpt-same',
    models: [],
    endpoints: [],
    endpoints_config: {
      'openai::https://openai.example/v1::chat_completions': {
        provider: 'openai',
        endpoint: 'https://openai.example/v1',
        wire_api: 'chat_completions',
        default_model: 'gpt-same',
        models: ['gpt-same', 'gpt-hidden'],
      },
      'openai::https://openai.example/v1::responses': {
        provider: 'openai',
        endpoint: 'https://openai.example/v1',
        wire_api: 'responses',
        default_model: 'gpt-same',
        models: ['gpt-same'],
      },
    },
    model_specs: [
      {
        name: 'openai::https://openai.example/v1::chat_completions::gpt-same',
        label: 'GPT Same Chat',
        provider: 'openai',
        endpoint: 'https://openai.example/v1',
        wire_api: 'chat_completions',
        model: 'gpt-same',
      },
      {
        name: 'openai::https://openai.example/v1::responses::gpt-same',
        label: 'GPT Same Responses',
        provider: 'openai',
        endpoint: 'https://openai.example/v1',
        wire_api: 'responses',
        model: 'gpt-same',
      },
      {
        name: 'openai::https://openai.example/v1::chat_completions::gpt-hidden',
        label: 'GPT Hidden',
        provider: 'openai',
        endpoint: 'https://openai.example/v1',
        wire_api: 'chat_completions',
        model: 'gpt-hidden',
        showInMenu: false,
      },
    ],
  })

  assert.deepEqual(
    choices.map((choice) => ({
      key: choice.key,
      label: choice.modelLabel,
      model: choice.model,
      wireApi: choice.wireApi,
    })),
    [
      {
        key: 'openai::https://openai.example/v1::chat_completions::gpt-same',
        label: 'GPT Same Chat',
        model: 'gpt-same',
        wireApi: 'chat_completions',
      },
      {
        key: 'openai::https://openai.example/v1::responses::gpt-same',
        label: 'GPT Same Responses',
        model: 'gpt-same',
        wireApi: 'responses',
      },
    ],
  )
})

test('selectDefaultLlmModelChoice skips disabled and unselectable model specs', () => {
  const registry = {
    provider: 'talkwise',
    default_model: 'disabled-model',
    models: [
      {
        name: 'disabled-model',
        provider: 'openai',
        is_default: true,
      },
      {
        name: 'enabled-model',
        provider: 'openai',
      },
      {
        name: 'unselectable-model',
        provider: 'openai',
      },
    ],
    endpoints: [],
    model_specs: [
      {
        name: 'disabled-model',
        label: 'Disabled Model',
        selectable: false,
        disabled_reason: 'Temporarily unavailable',
        preset: {
          endpoint: 'openai',
          model: 'disabled-model',
        },
      },
      {
        name: 'unselectable-model',
        label: 'Unselectable Model',
        unselectable: true,
        disabled_reason: 'Hidden from training runtime',
        preset: {
          endpoint: 'openai',
          model: 'unselectable-model',
        },
      },
    ],
  }
  const choices = llmRegistry.getLlmRegistryModelChoices(registry)
  const disabledChoice = choices.find((choice) => choice.model === 'disabled-model')
  const unselectableChoice = choices.find((choice) => choice.model === 'unselectable-model')

  assert.equal(disabledChoice.disabled, true)
  assert.equal(disabledChoice.disabledReason, 'Temporarily unavailable')
  assert.equal(unselectableChoice.disabled, true)
  assert.equal(unselectableChoice.disabledReason, 'Hidden from training runtime')
  assert.equal(llmRegistry.isLlmModelChoiceSelectable(disabledChoice), false)
  assert.equal(llmRegistry.isLlmModelChoiceSelectable(unselectableChoice), false)
  assert.equal(llmRegistry.selectDefaultLlmModelChoice(registry).model, 'enabled-model')
})

test('fetchLlmRegistry unwraps API responses and includes auth headers', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, init) => {
    assert.equal(url, llmRegistry.LLM_REGISTRY_API)
    assert.deepEqual(init.headers, { 'X-Mock-User': 'admin' })
    return new Response(JSON.stringify({
      code: 0,
      message: 'ok',
      data: registryPayload,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    const registry = await llmRegistry.fetchLlmRegistry()
    assert.equal(registry.provider, 'talkwise')
    assert.equal(registry.models.length, 2)
    assert.equal(registry.endpoints.length, 2)
  } finally {
    globalThis.fetch = originalFetch
  }
})
