import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTrainingStudioModule() {
  const sourcePath = path.resolve('src/services/trainingStudio.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  let outputText = output.outputText
  const cleanupPaths = []
  if (outputText.includes("from './auth'")) {
    const authSource = fs.readFileSync(path.resolve('src/services/auth.ts'), 'utf8')
    const authOutput = ts.transpileModule(authSource, {
      compilerOptions: {
        module: ts.ModuleKind.ES2022,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText
    const authPath = path.join(os.tmpdir(), `auth-service-${process.pid}-${Date.now()}.mjs`)
    fs.writeFileSync(authPath, authOutput)
    cleanupPaths.push(authPath)
    outputText = outputText.replace("from './auth'", `from '${pathToFileURL(authPath).href}'`)
  }
  const outputPath = path.join(os.tmpdir(), `training-studio-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
    cleanupPaths.forEach((cleanupPath) => fs.rmSync(cleanupPath, { force: true }))
  }
}

function createStorage(initialEntries = {}) {
  const entries = new Map(Object.entries(initialEntries))
  return {
    getItem(key) {
      return entries.has(key) ? entries.get(key) : null
    },
    setItem(key, value) {
      entries.set(key, String(value))
    },
    removeItem(key) {
      entries.delete(key)
    },
  }
}

const trainingStudio = await loadTrainingStudioModule()

test('default training studio config is product-manager interview oriented', () => {
  const config = trainingStudio.getDefaultTrainingStudioConfig()

  assert.equal(config.scenario, 'interview')
  assert.equal(config.interviewRolePreset, 'hiring_manager')
  assert.equal(config.interviewScenarioPreset, 'resume_deep_dive')
  assert.equal(config.role, 'Product Manager')
  assert.equal(config.replyLanguage, 'zh-CN')
  assert.match(config.techStack, /interview/i)
})

test('interview scenario presets carry realistic interviewer counterparts', () => {
  const resumeDeepDive = trainingStudio.getInterviewScenarioPreset('resume_deep_dive')
  const productCase = trainingStudio.getInterviewScenarioPreset('product_sense_case')

  assert.equal(resumeDeepDive.fallbackPersonaName, 'Hiring Manager')
  assert.match(resumeDeepDive.fallbackPersonaRole, /resume claims/i)
  assert.equal(productCase.framework, 'scqa')
})

test('product scenario presets carry realistic stakeholder counterparts', () => {
  const prdReview = trainingStudio.getProductScenarioPreset('prd_review')
  const executiveUpdate = trainingStudio.getProductScenarioPreset('executive_update')

  assert.equal(prdReview.fallbackPersonaName, 'Engineering Lead')
  assert.match(prdReview.fallbackPersonaRole, /feasibility/i)
  assert.equal(executiveUpdate.difficulty, 'hard')
})

test('buildTrainingStudioPrompt includes interview round and interviewer context', () => {
  const config = trainingStudio.getDefaultTrainingStudioConfig()
  const prompt = trainingStudio.buildTrainingStudioPrompt(config, 'Practice a resume deep dive.')

  assert.match(prompt, /Interview/)
  assert.match(prompt, /Interview round: Resume deep dive/)
  assert.match(prompt, /Interviewer: Hiring manager/)
  assert.match(prompt, /Interview focus: resume project/)
  assert.match(prompt, /AI reply language: Chinese \(Simplified\) \(zh-CN\)/)
  assert.match(prompt, /must reply in the selected language/)
})

test('buildTrainingStudioPrompt includes product drill and counterpart context', () => {
  const config = {
    ...trainingStudio.getDefaultTrainingStudioConfig(),
    scenario: 'product_management',
    productRolePreset: 'core_pm',
    productScenarioPreset: 'roadmap_prioritization',
  }
  const prompt = trainingStudio.buildTrainingStudioPrompt(config, 'Practice a roadmap trade-off.')

  assert.match(prompt, /Product Mgmt/)
  assert.match(prompt, /Product drill: Roadmap priority/)
  assert.match(prompt, /Counterpart: Head of Sales/)
  assert.match(prompt, /PM focus: roadmap prioritization/)
})

test('buildTrainingStudioPrompt omits product drill context outside product scenarios', () => {
  const config = {
    ...trainingStudio.getDefaultTrainingStudioConfig(),
    scenario: 'interview',
  }
  const prompt = trainingStudio.buildTrainingStudioPrompt(config, 'Practice an interview answer.')

  assert.doesNotMatch(prompt, /Product drill:/)
  assert.doesNotMatch(prompt, /Counterpart:/)
})

test('buildTrainingStudioCapabilityReadiness summarizes ready model and realtime foundations', () => {
  const readiness = trainingStudio.buildTrainingStudioCapabilityReadiness({
    modelChoices: [
      {
        provider: 'openai',
        providerLabel: 'OpenAI',
        model: 'gpt-4o',
        modelLabel: 'GPT-4o',
        capabilities: ['text', 'tools', 'mcp'],
        isDefault: true,
        disabled: false,
      },
    ],
    realtimeCapabilities: {
      pipecat: {
        available: true,
        coreAvailable: true,
        websocketAvailable: true,
        vadAvailable: true,
        sttAvailable: true,
        ttsAvailable: true,
        llmAvailable: true,
        turnDetectionAvailable: true,
        missingModules: [],
        optionalMissingModules: [],
        error: null,
        readyForCall: true,
        readiness: {
          ready: true,
          status: 'ready',
        },
      },
    },
  })

  assert.equal(readiness.overallStatus, 'ready')
  assert.equal(readiness.providerModel.status, 'ready')
  assert.equal(readiness.realtime.status, 'ready')
  assert.equal(readiness.agentMcp.status, 'ready')
  assert.equal(readiness.modelCounts.toolCapableModels, 1)
  assert.equal(readiness.modelCounts.mcpCapableModels, 1)
  assert.equal(readiness.realtimeCounts.pipecatReadyFeatures, 7)
})

test('buildTrainingStudioCapabilityReadiness trusts backend Pipecat readiness status', () => {
  const pipecat = {
    available: true,
    coreAvailable: true,
    websocketAvailable: true,
    vadAvailable: true,
    sttAvailable: true,
    ttsAvailable: true,
    llmAvailable: true,
    turnDetectionAvailable: true,
    missingModules: [],
    optionalMissingModules: [],
    error: null,
    readyForCall: false,
    readiness: {
      ready: false,
      status: 'blocked',
      blockingReasons: [
        {
          code: 'MISSING_OPENAI_API_KEY',
          message: 'backend readiness says the call cannot start',
        },
      ],
    },
  }

  const readiness = trainingStudio.buildTrainingStudioCapabilityReadiness({
    realtimeCapabilities: { pipecat },
  })

  assert.equal(trainingStudio.getPipecatReadinessStatus(pipecat), 'blocked')
  assert.equal(readiness.realtime.status, 'blocked')
  assert.equal(readiness.overallStatus, 'blocked')
  assert.equal(readiness.realtimeCounts.blockingIssues, 1)
  assert.equal(readiness.realtime.tags.includes('Pipecat blocked'), true)
})

test('buildTrainingStudioCapabilityReadiness marks tool-only agent readiness as warning', () => {
  const readiness = trainingStudio.buildTrainingStudioCapabilityReadiness({
    modelChoices: [
      {
        provider: 'anthropic',
        model: 'claude-sonnet',
        capabilities: ['text', 'tool_calling'],
        disabled: false,
      },
    ],
  })

  assert.equal(readiness.providerModel.status, 'ready')
  assert.equal(readiness.realtime.status, 'unknown')
  assert.equal(readiness.agentMcp.status, 'warning')
  assert.match(readiness.agentMcp.detail, /MCP server inventory/)
  assert.equal(readiness.modelCounts.toolCapableModels, 1)
  assert.equal(readiness.modelCounts.mcpCapableModels, 0)
})

test('buildTrainingStudioCapabilityReadiness surfaces realtime blockers without leaking secrets', () => {
  const readiness = trainingStudio.buildTrainingStudioCapabilityReadiness({
    modelChoices: [],
    realtimeCapabilities: {
      pipecat: {
        available: false,
        coreAvailable: false,
        websocketAvailable: false,
        vadAvailable: false,
        sttAvailable: false,
        ttsAvailable: false,
        llmAvailable: false,
        turnDetectionAvailable: false,
        missingModules: ['pipecat.services.openai'],
        optionalMissingModules: [],
        error: 'PIPECAT_MODULE_UNAVAILABLE',
        readyForCall: false,
        readiness: {
          ready: false,
          status: 'blocked',
          blockingReasons: [
            {
              code: 'PIPECAT_MODULE_UNAVAILABLE',
              modules: ['pipecat.services.openai'],
            },
          ],
        },
      },
    },
  })

  assert.equal(readiness.overallStatus, 'blocked')
  assert.equal(readiness.providerModel.status, 'unknown')
  assert.equal(readiness.realtime.status, 'blocked')
  assert.equal(readiness.realtimeCounts.blockingIssues, 1)
  assert.deepEqual(
    readiness.realtime.metrics.map((metric) => [metric.label, metric.value]),
    [
      ['pipecat features', '0/7'],
      ['blockers', '1'],
      ['missing modules', '1'],
    ],
  )
})

test('buildTrainingStudioCapabilityReadiness uses backend agent MCP inventory when present', () => {
  const readiness = trainingStudio.buildTrainingStudioCapabilityReadiness({
    modelChoices: [
      {
        provider: 'openai',
        model: 'gpt-4o-mini',
        capabilities: ['text'],
        disabled: false,
      },
    ],
    capabilityRegistry: {
      provider: 'talkwise',
      version: 1,
      capabilities: [
        {
          id: 'agent:training-coach',
          kind: 'agent',
          name: 'Training Coach',
          status: 'available',
          enabled: true,
          readiness: { ready: true, status: 'ready' },
        },
        {
          id: 'tool:branch-review',
          kind: 'tool',
          name: 'Branch Review Tool',
          status: 'available',
          enabled: true,
          readiness: { ready: true, status: 'ready' },
        },
        {
          id: 'mcp:local-memory',
          kind: 'mcp_server',
          name: 'Local Memory',
          status: 'available',
          enabled: true,
          readiness: { ready: true, status: 'ready' },
        },
      ],
    },
  })

  assert.equal(readiness.agentMcp.status, 'ready')
  assert.match(readiness.agentMcp.detail, /Backend agent and MCP inventory/)
  assert.deepEqual(
    readiness.agentMcp.metrics.map((metric) => [metric.label, metric.value]),
    [
      ['tool models', '0'],
      ['MCP models', '0'],
      ['inventory', '3'],
      ['blocked', '0'],
      ['selectable', '1'],
    ],
  )
})

test('buildTrainingStudioCapabilityReadiness redacts backend capability blockers', () => {
  const readiness = trainingStudio.buildTrainingStudioCapabilityReadiness({
    modelChoices: [
      {
        provider: 'openai',
        model: 'gpt-4o-mini',
        capabilities: ['text'],
        disabled: false,
      },
    ],
    capabilityRegistry: {
      capabilities: [
        {
          id: 'mcp:remote',
          kind: 'mcp_server',
          name: 'Remote MCP',
          status: 'missingDependency',
          enabled: true,
          readiness: {
            ready: false,
            status: 'blocked',
            blockingReasons: [
              {
                code: 'MCP_AUTH_FAILED',
                message: 'authorization=Bearer sk-secret-token-123456',
              },
            ],
          },
        },
      ],
    },
  })

  assert.equal(readiness.agentMcp.status, 'blocked')
  assert.match(readiness.agentMcp.tags.join(' '), /authorization=\*\*\*/)
  assert.doesNotMatch(JSON.stringify(readiness.agentMcp), /sk-secret-token/)
})

test('uploadVideoAnswer binds training session and auth context into the request', async () => {
  const originalWindow = globalThis.window
  const originalFetch = globalThis.fetch
  const localStorage = createStorage({
    'talkwise.auth.state': JSON.stringify({ status: 'authenticated', userId: 'leader' }),
  })
  const sessionStorage = createStorage()
  globalThis.window = { localStorage, sessionStorage }

  const blob = new Blob(['video-bytes'], { type: 'video/webm' })
  const expectedUploadUrl = '/api/v1/training-studio/video-answers?training_session_id=session-7&room_id=42'
  const expectedPlaybackUrl = '/api/v1/training-studio/video-answers/answer-1.webm?training_session_id=session-7&room_id=42&auth_user_id=user-leader-001&auth_role=leader&auth_team_id=team-revenue'
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init })
    assert.equal(String(url), expectedUploadUrl)
    assert.equal(init.method, 'POST')
    assert.equal(init.body, blob)
    assert.equal(init.headers['Content-Type'], 'video/webm')
    assert.equal(init.headers['X-Filename'], 'answer.webm')
    assert.equal(init.headers['X-Mock-User'], 'leader')
    assert.equal(init.headers['X-User-Id'], 'user-leader-001')
    assert.equal(init.headers['X-System-Role'], 'leader')
    assert.equal(init.headers['X-Team-Id'], 'team-revenue')
    return new Response(JSON.stringify({
      data: {
        filename: 'answer-1.webm',
        url: expectedPlaybackUrl,
        mimeType: 'video/webm',
        size: blob.size,
      },
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    const result = await trainingStudio.uploadVideoAnswer(blob, {
      trainingSessionId: 'session-7',
      roomId: 42,
      filename: 'answer.webm',
    })

    assert.equal(result.filename, 'answer-1.webm')
    assert.equal(result.url, expectedPlaybackUrl)
    assert.equal(result.mimeType, 'video/webm')
    assert.equal(result.size, blob.size)
    assert.equal(calls.length, 1)
  } finally {
    globalThis.fetch = originalFetch
    globalThis.window = originalWindow
  }
})
