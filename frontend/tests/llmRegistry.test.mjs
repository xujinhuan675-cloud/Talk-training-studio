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
