import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTsModule(sourcePath, prefix, transformSource = (source) => source) {
  const source = transformSource(fs.readFileSync(path.resolve(sourcePath), 'utf8'))
  let outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(os.tmpdir(), `${prefix}-${process.pid}-${Date.now()}.mjs`)
  const cleanupPaths = [outputPath]

  if (outputText.includes("from './scenarioConfig'")) {
    const dependencySource = fs.readFileSync(path.resolve('src/data/scenarioConfig.ts'), 'utf8')
    const dependencyOutput = ts.transpileModule(dependencySource, {
      compilerOptions: {
        module: ts.ModuleKind.ES2022,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText
    const dependencyPath = path.join(os.tmpdir(), `scenario-config-dependency-${process.pid}-${Date.now()}.mjs`)
    fs.writeFileSync(dependencyPath, dependencyOutput)
    cleanupPaths.push(dependencyPath)
    outputText = outputText.replace(
      "from './scenarioConfig'",
      `from '${pathToFileURL(dependencyPath).href}'`,
    )
  }
  if (outputText.includes("from '../data/scenarioConfig'")) {
    const dependencySource = fs.readFileSync(path.resolve('src/data/scenarioConfig.ts'), 'utf8')
    const dependencyOutput = ts.transpileModule(dependencySource, {
      compilerOptions: {
        module: ts.ModuleKind.ES2022,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText
    const dependencyPath = path.join(os.tmpdir(), `scenario-config-service-dependency-${process.pid}-${Date.now()}.mjs`)
    fs.writeFileSync(dependencyPath, dependencyOutput)
    cleanupPaths.push(dependencyPath)
    outputText = outputText.replace(
      "from '../data/scenarioConfig'",
      `from '${pathToFileURL(dependencyPath).href}'`,
    )
  }
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

  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    cleanupPaths.forEach((item) => fs.rmSync(item, { force: true }))
  }
}

const scenarioTrainingService = await loadTsModule('src/services/scenarioTraining.ts', 'scenario-training-service')
const scenarioConfigService = await loadTsModule('src/services/scenarioConfig.ts', 'scenario-config-service')
const scenarioTrainingData = await loadTsModule('src/data/trainingScenarios.ts', 'scenario-training-data')
const scenarioConfigData = await loadTsModule('src/data/scenarioConfig.ts', 'scenario-config-data')
const expectedAuthHeaders = {
  'X-Mock-User': 'admin',
  'X-User-Id': 'user-admin-001',
  'X-System-Role': 'admin',
  'X-Team-Id': 'team-ops',
}

test('fetchScenarioTrainingCatalog reads backend templates and maps card fields', async () => {
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        code: 0,
        message: 'ok',
        data: [
          {
            id: 'new-customer-discount',
            title: '新客优惠咨询',
            description: '门店新客想了解价格。',
            customer_profile: '首次到店客户',
            difficulty: 'easy',
            category: 'sales',
            required: true,
            status: 'not_started',
            score: null,
            last_practiced_at: null,
            opening_line: '你好，我看到你们门口说有新客优惠，能介绍一下吗？',
            persona: {
              name: '李女士',
              role: '预算敏感的新客',
              style: '友好但谨慎',
            },
            learner_role: 'Salesperson',
            framework: 'prep',
            dimension_weights: [
              { dimension_id: 'substance', weight: 40 },
              { dimension_id: 'structure', weight: 20 },
              { dimension_id: 'relevance', weight: 20 },
              { dimension_id: 'credibility', weight: 10 },
              { dimension_id: 'differentiation', weight: 10 },
            ],
            training_points: ['快速建立信任'],
          },
        ],
      }),
    }
  }

  const result = await scenarioTrainingService.fetchScenarioTrainingCatalog()

  assert.equal(calls[0].url, '/api/v1/training-studio/scenario-templates')
  assert.deepEqual(calls[0].init, { headers: expectedAuthHeaders })
  assert.deepEqual(result, [
    {
      id: 'new-customer-discount',
      title: '新客优惠咨询',
      description: '门店新客想了解价格。',
      customerProfile: '首次到店客户',
      difficulty: 'easy',
      category: 'sales',
      required: true,
      status: 'not_started',
      score: undefined,
      lastPracticedAt: undefined,
      openingLine: '你好，我看到你们门口说有新客优惠，能介绍一下吗？',
      persona: {
        name: '李女士',
        role: '预算敏感的新客',
        style: '友好但谨慎',
      },
      learnerRole: 'Salesperson',
      framework: 'prep',
      dimensionWeights: [
        { dimensionId: 'substance', weight: 40 },
        { dimensionId: 'structure', weight: 20 },
        { dimensionId: 'relevance', weight: 20 },
        { dimensionId: 'credibility', weight: 10 },
        { dimensionId: 'differentiation', weight: 10 },
      ],
      trainingPoints: ['快速建立信任'],
    },
  ])
})

test('fetchScenarioTrainingCatalog surfaces backend error messages', async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 503,
    json: async () => ({ detail: 'scenario templates unavailable' }),
  })

  await assert.rejects(
    scenarioTrainingService.fetchScenarioTrainingCatalog(),
    /scenario templates unavailable/,
  )
})

test('fetchScenarioTrainingProgress reads backend progress and maps card status', async () => {
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        code: 0,
        message: 'ok',
        data: [
          {
            scenario_id: 'new-customer-discount',
            user_id: 'user-sales-001',
            team_id: 'team-revenue',
            status: 'completed',
            score: 84,
            score_status: 'ready',
            overall_score: 4.2,
            evaluation_id: 12,
            last_practiced_at: '2026-07-15T05:00:00Z',
            training_session_id: 'session-1',
            report_id: '9001',
            score_id: null,
            failure_reason: null,
          },
        ],
      }),
    }
  }

  const result = await scenarioTrainingService.fetchScenarioTrainingProgress({
    userId: 'user-sales-001',
    teamId: 'team-revenue',
  })

  assert.equal(calls[0].url, '/api/v1/training-studio/scenario-progress?user_id=user-sales-001&team_id=team-revenue')
  assert.deepEqual(calls[0].init, { headers: expectedAuthHeaders })
  assert.deepEqual(result, {
    'new-customer-discount': {
      status: 'completed',
      score: 84,
      scoreStatus: 'ready',
      overallScore: 4.2,
      evaluationId: 12,
      lastPracticedAt: '2026-07-15T05:00:00Z',
      userId: 'user-sales-001',
      teamId: 'team-revenue',
      trainingSessionId: 'session-1',
      reportId: '9001',
      scoreId: undefined,
      failureReason: undefined,
    },
  })
})

test('fetchScenarioTrainingProgress maps failed progress failure reason', async () => {
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      code: 0,
      message: 'ok',
      data: [
        {
          scenario_id: 'refund-service-recovery',
          status: 'failed',
          score: null,
          score_status: 'pending',
          overall_score: null,
          evaluation_id: null,
          last_practiced_at: '2026-07-15T05:00:00Z',
          training_session_id: 'session-failed',
          report_id: null,
          score_id: null,
          failure_reason: 'report generation timed out',
        },
      ],
    }),
  })

  const result = await scenarioTrainingService.fetchScenarioTrainingProgress()

  assert.deepEqual(result['refund-service-recovery'], {
    status: 'failed',
    score: undefined,
    scoreStatus: 'pending',
    overallScore: undefined,
    evaluationId: undefined,
    lastPracticedAt: '2026-07-15T05:00:00Z',
    userId: undefined,
    teamId: undefined,
    trainingSessionId: 'session-failed',
    reportId: undefined,
    scoreId: undefined,
    failureReason: 'report generation timed out',
  })
})

test('fetchScenarioConfig reads backend config and sends auth headers', async () => {
  const calls = []
  const remoteScenario = {
    id: 'remote-sales',
    title: 'Remote sales drill',
    description: 'Handle a concrete buyer objection.',
    customerProfile: 'Budget-sensitive buyer',
    difficulty: 'medium',
    category: 'sales',
    required: true,
    enabled: true,
    openingLine: 'Why is this worth the price?',
    persona: {
      name: 'Buyer',
      role: 'Decision maker',
      style: 'Direct and skeptical.',
    },
    learnerRole: 'Salesperson',
    framework: 'prep',
    trainingPoints: ['Listen first', 'Explain trade-offs'],
    dimensionWeights: [
      { dimensionId: 'substance', weight: 60 },
      { dimensionId: 'structure', weight: 40 },
    ],
    updatedAt: '2026-07-15T02:00:00.000Z',
  }
  const remoteDimension = {
    id: 'custom-tone',
    name: 'Tone',
    description: 'Keeps the answer direct without sounding defensive.',
    enabled: false,
    source: 'local',
    updatedAt: '2026-07-15T02:00:00.000Z',
  }

  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        code: 0,
        message: 'ok',
        data: {
          scenarios: [remoteScenario],
          dimensions: [remoteDimension],
          selectedScenarioId: 'remote-sales',
          selectedDimensionId: 'custom-tone',
          updated_at: '2026-07-15T03:00:00.000Z',
        },
      }),
    }
  }

  const result = await scenarioConfigService.fetchScenarioConfig([], {
    version: 1,
    scenarios: [],
    dimensions: [],
    selectedScenarioId: 'remote-sales',
    selectedDimensionId: 'custom-tone',
    updatedAt: '2026-07-15T01:00:00.000Z',
  })

  assert.equal(calls[0].url, '/api/v1/training-studio/scenario-config')
  assert.deepEqual(calls[0].init, { headers: expectedAuthHeaders })
  assert.equal(result.updatedAt, '2026-07-15T03:00:00.000Z')
  assert.equal(result.selectedScenarioId, 'remote-sales')
  assert.equal(result.selectedDimensionId, 'custom-tone')
  assert.equal(result.scenarios[0].customerProfile, 'Budget-sensitive buyer')
  assert.deepEqual(result.scenarios[0].dimensionWeights, [
    { dimensionId: 'substance', weight: 60 },
    { dimensionId: 'structure', weight: 40 },
  ])
  assert.equal(result.dimensions.find((dimension) => dimension.id === 'custom-tone').enabled, false)
})

test('saveScenarioConfig puts backend config document with auth headers', async () => {
  const draft = scenarioConfigData.createBlankScenarioDraft({
    id: 'local-objection-handling',
    title: 'Objection handling',
    dimensionWeights: [
      { dimensionId: 'substance', weight: 60 },
      { dimensionId: 'structure', weight: 40 },
    ],
  })
  const state = scenarioConfigData.upsertScenarioConfigDraft(
    scenarioConfigData.createScenarioConfigState([]),
    draft,
  )
  const calls = []

  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        scenarios: state.scenarios,
        dimensions: state.dimensions,
        selectedScenarioId: state.selectedScenarioId,
        selectedDimensionId: state.selectedDimensionId,
        updated_at: '2026-07-15T04:00:00.000Z',
      }),
    }
  }

  const result = await scenarioConfigService.saveScenarioConfig(state, [])
  const body = JSON.parse(calls[0].init.body)

  assert.equal(calls[0].url, '/api/v1/training-studio/scenario-config')
  assert.equal(calls[0].init.method, 'PUT')
  assert.deepEqual(calls[0].init.headers, {
    ...expectedAuthHeaders,
    'Content-Type': 'application/json',
  })
  assert.deepEqual(Object.keys(body).sort(), ['dimensions', 'scenarios', 'selectedDimensionId', 'selectedScenarioId', 'updated_at'])
  assert.deepEqual(body.scenarios, JSON.parse(JSON.stringify(state.scenarios)))
  assert.deepEqual(body.dimensions, JSON.parse(JSON.stringify(state.dimensions)))
  assert.equal(body.selectedScenarioId, state.selectedScenarioId)
  assert.equal(body.selectedDimensionId, state.selectedDimensionId)
  assert.equal(body.updated_at, state.updatedAt)
  assert.equal(result.updatedAt, '2026-07-15T04:00:00.000Z')
  assert.equal(result.selectedScenarioId, state.selectedScenarioId)
})

test('scenario task config maps MVP card values to Training Studio enums', () => {
  const customerServiceScenario = scenarioTrainingData.scenarioTrainingCatalog.find(
    (item) => item.category === 'customer_service',
  )
  const expertScenario = scenarioTrainingData.scenarioTrainingCatalog.find(
    (item) => item.difficulty === 'expert',
  )

  assert.ok(customerServiceScenario)
  assert.ok(expertScenario)

  const serviceConfig = scenarioTrainingData.buildScenarioTrainingTaskConfig(customerServiceScenario)
  const expertConfig = scenarioTrainingData.buildScenarioTrainingTaskConfig(expertScenario)
  const drillConfig = scenarioTrainingData.buildScenarioTrainingTaskConfig(customerServiceScenario, {
    feedbackMode: 'drill',
  })

  assert.equal(serviceConfig.category, 'workplace')
  assert.equal(expertConfig.difficulty, 'hard')
  assert.equal(expertConfig.category, 'negotiation')
  assert.equal(expertConfig.metadata.source, 'scenario_training')
  assert.equal(serviceConfig.metadata.feedbackMode, 'simulation')
  assert.equal(serviceConfig.metadata.trainingFeedbackMode, 'simulation')
  assert.equal(expertConfig.metadata.scenario_training.id, expertScenario.id)
  assert.equal(drillConfig.metadata.feedbackMode, 'drill')
  assert.equal(drillConfig.metadata.trainingFeedbackMode, 'drill')
  assert.equal(drillConfig.metadata.feedbackPolicy.mode, 'drill')
  assert.equal(drillConfig.metadata.feedbackPolicy.channelAgnostic, true)
  assert.equal(drillConfig.metadata.scenario_training.feedbackMode, 'drill')
  assert.deepEqual(serviceConfig.rubric_weights, {
    substance: 0.25,
    structure: 0.2,
    relevance: 0.25,
    credibility: 0.2,
    differentiation: 0.1,
  })
  assert.deepEqual(serviceConfig.metadata.scenario_training.dimension_weights, [
    { dimensionId: 'substance', weight: 25 },
    { dimensionId: 'structure', weight: 20 },
    { dimensionId: 'relevance', weight: 25 },
    { dimensionId: 'credibility', weight: 20 },
    { dimensionId: 'differentiation', weight: 10 },
  ])
})

test('scenario task config prefers configured dimension weights', () => {
  const scenario = {
    ...scenarioTrainingData.scenarioTrainingCatalog[0],
    dimensionWeights: [
      { dimensionId: 'substance', weight: 40 },
      { dimensionId: 'structure', weight: 20 },
      { dimensionId: 'relevance', weight: 20 },
      { dimensionId: 'credibility', weight: 10 },
      { dimensionId: 'differentiation', weight: 10 },
    ],
  }

  const config = scenarioTrainingData.buildScenarioTrainingTaskConfig(scenario)

  assert.deepEqual(config.rubric_weights, {
    substance: 0.4,
    structure: 0.2,
    relevance: 0.2,
    credibility: 0.1,
    differentiation: 0.1,
  })
  assert.deepEqual(config.metadata.scenario_training.dimension_weights, scenario.dimensionWeights)
})

test('scenario prompts carry realistic customer simulation rules', () => {
  const scenario = scenarioTrainingData.scenarioTrainingCatalog.find(
    (item) => item.id === 'new-customer-discount',
  )

  assert.ok(scenario)

  const prompt = scenarioTrainingData.buildScenarioTrainingPrompt(scenario, 'text')
  const drillPrompt = scenarioTrainingData.buildScenarioTrainingPrompt(scenario, 'text', {
    feedbackMode: 'drill',
  })
  const payload = scenarioTrainingData.buildScenarioTrainingRuntimePersona(scenario, 'text')
  const drillPayload = scenarioTrainingData.buildScenarioTrainingRuntimePersona(scenario, 'voice', {
    feedbackMode: 'drill',
  })

  assert.match(prompt, /not a cooperative demo/)
  assert.match(prompt, /30-120 Chinese characters/)
  assert.match(prompt, /Do not reveal all needs, budget, objections, or bottom lines at once/)
  assert.match(prompt, /never score the learner/)
  assert.match(prompt, /complete simulation/)
  assert.match(prompt, /Difficulty behavior:/)
  assert.match(payload.style, /Speak like a real counterpart/)
  assert.match(payload.style, /Feedback mode: simulation/)
  assert.deepEqual(payload.training_points, scenario.trainingPoints)
  assert.match(drillPrompt, /deliberate drill/)
  assert.match(drillPrompt, /one concise correction, one stronger rewrite/)
  assert.doesNotMatch(drillPrompt, /never give coaching advice/)
  assert.match(drillPayload.style, /Run deliberate drill turns/)
  assert.match(drillPayload.style, /Feedback mode: drill/)
})

test('scenario runtime persona preserves catalog-sized training point lists', () => {
  const scenario = scenarioTrainingData.scenarioTrainingCatalog.find(
    (item) => item.id === 'ai-web3-agent-pm-comprehensive-interview',
  )

  assert.ok(scenario)

  const payload = scenarioTrainingData.buildScenarioTrainingRuntimePersona(scenario, 'voice')

  assert.equal(payload.training_points.length, 6)
  assert.deepEqual(payload.training_points, scenario.trainingPoints)
})

test('scenario context helpers find catalog cards and session-linked progress', () => {
  const card = scenarioTrainingData.getScenarioTrainingCardById(' new-customer-discount ')

  assert.ok(card)
  assert.equal(card.id, 'new-customer-discount')
  assert.equal(scenarioTrainingData.getScenarioTrainingCardById('missing-scenario'), null)
  assert.equal(scenarioTrainingData.getScenarioTrainingCardById('   '), null)

  const progress = {
    'new-customer-discount': {
      status: 'in_progress',
      trainingSessionId: 'session-1',
    },
    'enterprise-demo-objection': {
      status: 'completed',
      trainingSessionId: 'session-2',
    },
  }

  assert.equal(scenarioTrainingData.findScenarioTrainingIdBySession(progress, ' session-2 '), 'enterprise-demo-objection')
  assert.equal(scenarioTrainingData.findScenarioTrainingIdBySession(progress, 'missing-session'), null)
  assert.equal(scenarioTrainingData.findScenarioTrainingIdBySession(progress, null), null)
})

test('scenario route state carries full chat context without sharing mutable arrays', () => {
  const scenario = scenarioTrainingData.scenarioTrainingCatalog.find(
    (item) => item.id === 'new-customer-discount',
  )

  assert.ok(scenario)

  const state = scenarioTrainingData.buildScenarioTrainingRouteState(scenario, {
    feedbackMode: 'assisted',
  })

  assert.equal(state.source, 'scenario-training')
  assert.equal(state.scenarioTrainingId, scenario.id)
  assert.equal(state.scenarioTitle, scenario.title)
  assert.equal(state.scenarioDescription, scenario.description)
  assert.equal(state.scenarioCustomerProfile, scenario.customerProfile)
  assert.equal(state.scenarioOpeningLine, scenario.openingLine)
  assert.equal(state.scenarioPersonaName, scenario.persona.name)
  assert.equal(state.scenarioPersonaRole, scenario.persona.role)
  assert.equal(state.scenarioPersonaStyle, scenario.persona.style)
  assert.equal(state.scenarioLearnerRole, scenario.learnerRole)
  assert.equal(state.scenarioDifficulty, scenario.difficulty)
  assert.equal(state.scenarioCategory, scenario.category)
  assert.equal(state.scenarioRequired, scenario.required)
  assert.equal(state.trainingFeedbackMode, 'assisted')
  assert.deepEqual(state.scenarioTrainingPoints, scenario.trainingPoints)
  assert.notEqual(state.scenarioTrainingPoints, scenario.trainingPoints)
})

test('scenario progress helpers persist completion metadata', () => {
  const completed = scenarioTrainingData.markScenarioTrainingCompleted(
    {
      'new-customer-discount': {
        status: 'in_progress',
        lastPracticedAt: '2026-07-14T05:00:00Z',
        trainingSessionId: 'session-1',
      },
    },
    'new-customer-discount',
    {
      trainingSessionId: 'session-1',
      reportId: 9001,
      scoreId: 'score-1',
      completedAt: '2026-07-15T05:00:00Z',
    },
  )

  assert.deepEqual(completed['new-customer-discount'], {
    status: 'completed',
    score: undefined,
    scoreStatus: undefined,
    overallScore: undefined,
    evaluationId: undefined,
    lastPracticedAt: '2026-07-15T05:00:00Z',
    userId: undefined,
    teamId: undefined,
    trainingSessionId: 'session-1',
    reportId: '9001',
    scoreId: 'score-1',
  })
})

test('scenario progress helpers keep session ids and do not erase existing scores', () => {
  const started = scenarioTrainingData.markScenarioTrainingStarted(
    {},
    'new-customer-discount',
    'session-1',
    new Date('2026-07-14T05:00:00Z'),
  )

  assert.equal(started['new-customer-discount'].trainingSessionId, 'session-1')

  const merged = scenarioTrainingData.mergeScenarioTrainingProgressRecords(
    {
      'new-customer-discount': {
        status: 'completed',
        score: 92,
        lastPracticedAt: '2026-07-14T05:00:00Z',
        trainingSessionId: 'session-1',
      },
    },
    {
      'new-customer-discount': {
        status: 'completed',
        lastPracticedAt: '2026-07-15T05:00:00Z',
        scoreStatus: 'pending',
        trainingSessionId: 'session-1',
        reportId: '9001',
      },
    },
  )

  assert.deepEqual(merged['new-customer-discount'], {
    status: 'completed',
    score: 92,
    scoreStatus: 'pending',
    overallScore: undefined,
    evaluationId: undefined,
    lastPracticedAt: '2026-07-15T05:00:00Z',
    userId: undefined,
    teamId: undefined,
    trainingSessionId: 'session-1',
    reportId: '9001',
    scoreId: undefined,
    failureReason: undefined,
  })
})

test('scenario progress helpers preserve failure reasons while merging metadata', () => {
  const merged = scenarioTrainingData.mergeScenarioTrainingProgressRecords(
    {
      'refund-service-recovery': {
        status: 'failed',
        failureReason: 'report generation timed out',
        lastPracticedAt: '2026-07-15T05:00:00Z',
        trainingSessionId: 'session-failed',
      },
    },
    {
      'refund-service-recovery': {
        status: 'failed',
        scoreStatus: 'pending',
        lastPracticedAt: '2026-07-15T05:05:00Z',
      },
    },
  )

  assert.equal(merged['refund-service-recovery'].failureReason, 'report generation timed out')
  assert.equal(merged['refund-service-recovery'].scoreStatus, 'pending')
})

test('scenario leaderboard summary ranks only fully completed required drills', () => {
  const catalog = scenarioTrainingData.scenarioTrainingCatalog
  const required = catalog.filter((scenario) => scenario.required)
  const [firstRequired, secondRequired, thirdRequired] = required

  const completedProgress = Object.fromEntries(
    required.map((scenario, index) => [
      scenario.id,
      {
        status: 'completed',
        score: [90, 80, 70][index] ?? 75,
        lastPracticedAt: `2026-07-${10 + index}T05:00:00Z`,
      },
    ]),
  )
  const summary = scenarioTrainingData.buildScenarioLeaderboardSummary(
    catalog,
    [
      {
        userId: 'u-ranked',
        name: 'Ranked User',
        teamId: 'team-revenue',
        teamName: 'Revenue Team',
        progress: completedProgress,
      },
      {
        userId: 'u-partial',
        name: 'Partial User',
        teamId: 'team-revenue',
        teamName: 'Revenue Team',
        progress: {
          [firstRequired.id]: {
            status: 'completed',
            score: 60,
            lastPracticedAt: '2026-07-12T05:00:00Z',
          },
          [secondRequired.id]: {
            status: 'in_progress',
            scoreStatus: 'pending',
            lastPracticedAt: '2026-07-13T05:00:00Z',
          },
        },
      },
      {
        userId: 'u-idle',
        name: 'Idle User',
        teamId: 'team-revenue',
        teamName: 'Revenue Team',
        progress: {},
      },
    ],
    'u-partial',
  )

  assert.equal(summary.totalRequired, required.length)
  assert.equal(summary.team.ranked, 1)
  assert.equal(summary.team.ranks[0].userId, 'u-ranked')
  assert.equal(summary.team.ranks[0].averageScore, 80)
  assert.equal(summary.team.unfinishedAll, 2)
  assert.equal(summary.team.unfinishedActive, 1)

  const partial = summary.team.unfinished.find((row) => row.userId === 'u-partial')
  assert.ok(partial)
  assert.equal(partial.completedRequired, 1)
  assert.deepEqual(
    partial.unfinishedRequired.map((scenario) => scenario.scenarioId).sort(),
    [secondRequired.id, thirdRequired.id].sort(),
  )
  assert.equal(summary.personal.status, 'partial')
  assert.equal(summary.personal.completedRequired, 1)
})

test('scenario leaderboard ability dimensions use scored scenario aggregates', () => {
  const catalog = scenarioTrainingData.scenarioTrainingCatalog
  const required = catalog.filter((scenario) => scenario.required)
  const summary = scenarioTrainingData.buildScenarioLeaderboardSummary(
    catalog,
    [
      {
        userId: 'u-ranked',
        name: 'Ranked User',
        teamId: 'team-revenue',
        teamName: 'Revenue Team',
        progress: Object.fromEntries(
          required.map((scenario, index) => [
            scenario.id,
            {
              status: 'completed',
              score: [65, 75, 85][index] ?? 80,
              lastPracticedAt: `2026-07-${12 + index}T05:00:00Z`,
            },
          ]),
        ),
      },
    ],
    'u-ranked',
  )

  assert.ok(summary.team.weakDimensions.length > 0)
  const valueDimension = summary.team.weakDimensions.find((dimension) => dimension.dimensionId === 'value_clarity')
  assert.ok(valueDimension)
  assert.equal(valueDimension.sampleCount >= 1, true)
  assert.equal(valueDimension.scenarioTitles.length >= 1, true)
  assert.equal(summary.personal.abilityProfile.length > 0, true)
})

test('scenario leaderboard catalog fallback stays scoped to the opted-in user', () => {
  const [first, second] = scenarioTrainingData.scenarioTrainingCatalog
  const catalog = [
    { ...first, id: 'required-a', required: true, status: 'completed', score: 91 },
    { ...second, id: 'required-b', required: true, status: 'completed', score: 81 },
  ]

  const summary = scenarioTrainingData.buildScenarioLeaderboardSummary(
    catalog,
    [
      {
        userId: 'u-current',
        name: 'Current User',
        teamId: 'team-revenue',
        teamName: 'Revenue Team',
        progress: {},
        useCatalogFallback: true,
      },
      {
        userId: 'u-other',
        name: 'Other User',
        teamId: 'team-revenue',
        teamName: 'Revenue Team',
        progress: {},
      },
    ],
    'u-current',
  )

  assert.equal(summary.team.ranked, 1)
  assert.equal(summary.team.ranks[0].userId, 'u-current')
  assert.equal(summary.team.ranks[0].averageScore, 86)
  assert.equal(summary.team.unfinished[0].userId, 'u-other')
  assert.equal(summary.team.unfinished[0].completedRequired, 0)
  assert.equal(summary.personal.status, 'ranked')
})

test('scenario config default weights validate to 100 percent by category', () => {
  for (const category of ['sales', 'customer_service', 'negotiation', 'interview']) {
    const weights = scenarioConfigData.getDefaultDimensionWeights(category)
    const validation = scenarioConfigData.validateScenarioWeightTotal(weights)

    assert.equal(validation.valid, true)
    assert.equal(validation.total, 100)
  }
})

test('scenario config default dimensions expose localized display copy', () => {
  const localization = scenarioConfigData.DEFAULT_SCENARIO_DIMENSION_LOCALIZATION

  assert.equal(localization.substance.name[0], '内容质量')
  assert.equal(localization.substance.name[1], 'Substance')
  assert.match(localization.structure.description[0], /表达是否易于跟随/)
  assert.match(localization.structure.description[1], /easy to follow/)
})

test('scenario config seeds local drafts from the scenario catalog', () => {
  const state = scenarioConfigData.createScenarioConfigState(scenarioTrainingData.scenarioTrainingCatalog)

  assert.equal(state.scenarios.length, scenarioTrainingData.scenarioTrainingCatalog.length)
  assert.equal(state.dimensions.length >= 5, true)
  assert.equal(state.selectedScenarioId, scenarioTrainingData.scenarioTrainingCatalog[0].id)

  for (const scenario of state.scenarios) {
    assert.equal(scenarioConfigData.validateScenarioWeightTotal(scenario.dimensionWeights).valid, true)
  }
})

test('scenario config keeps the comprehensive job interview template as a full interview flow', () => {
  const scenario = scenarioTrainingData.scenarioTrainingCatalog.find(
    (item) => item.id === 'ai-web3-agent-pm-comprehensive-interview',
  )

  assert.ok(scenario)
  assert.equal(scenario.category, 'interview')
  assert.equal(scenario.framework, 'star')
  assert.equal(scenario.trainingPoints.length >= 6, true)

  const scenarioText = [
    scenario.description,
    scenario.customerProfile,
    scenario.openingLine,
    scenario.persona.style,
    ...scenario.trainingPoints,
  ].join('\n')

  for (const marker of ['AI Agent', 'Web3', 'XStable', 'NOFX', 'OpenEvolve']) {
    assert.match(scenarioText, new RegExp(marker))
  }

  const state = scenarioConfigData.createScenarioConfigState(scenarioTrainingData.scenarioTrainingCatalog)
  const draft = state.scenarios.find((item) => item.id === scenario.id)

  assert.ok(draft)
  assert.equal(draft.category, 'interview')
  assert.equal(scenarioConfigData.validateScenarioWeightTotal(draft.dimensionWeights).valid, true)
  assert.deepEqual(draft.dimensionWeights, [
    { dimensionId: 'substance', weight: 30 },
    { dimensionId: 'structure', weight: 20 },
    { dimensionId: 'relevance', weight: 20 },
    { dimensionId: 'credibility', weight: 15 },
    { dimensionId: 'differentiation', weight: 15 },
  ])
})

test('scenario config weight helpers sanitize input and distribute evenly', () => {
  assert.equal(scenarioConfigData.normalizeScenarioWeight('140'), 100)
  assert.equal(scenarioConfigData.normalizeScenarioWeight('-2'), 0)
  assert.equal(scenarioConfigData.normalizeScenarioWeight('abc'), 0)

  const weights = scenarioConfigData.distributeScenarioWeights(['a', 'b', 'c'])
  assert.deepEqual(weights, [
    { dimensionId: 'a', weight: 34 },
    { dimensionId: 'b', weight: 33 },
    { dimensionId: 'c', weight: 33 },
  ])
  assert.equal(scenarioConfigData.validateScenarioWeightTotal(weights).valid, true)

  const invalid = scenarioConfigData.validateScenarioWeightTotal([
    { dimensionId: 'a', weight: 50 },
    { dimensionId: 'b', weight: 40 },
  ])
  assert.equal(invalid.valid, false)
  assert.match(invalid.message, /100%/)
})

test('scenario config dimension updates keep existing scenario references', () => {
  const state = scenarioConfigData.createScenarioConfigState(scenarioTrainingData.scenarioTrainingCatalog)
  const firstDimension = state.dimensions[0]
  const nextState = scenarioConfigData.upsertScenarioDimension(state, {
    ...firstDimension,
    enabled: false,
  })

  assert.equal(nextState.dimensions.find((dimension) => dimension.id === firstDimension.id).enabled, false)
  assert.equal(
    nextState.scenarios.some((scenario) => (
      scenario.dimensionWeights.some((item) => item.dimensionId === firstDimension.id)
    )),
    true,
  )
})

test('scenario config upserts local scenario drafts with normalized weight values', () => {
  const state = scenarioConfigData.createScenarioConfigState([])
  const draft = scenarioConfigData.createBlankScenarioDraft({
    id: 'local-objection-handling',
    title: 'Objection handling',
    dimensionWeights: [
      { dimensionId: 'substance', weight: 60 },
      { dimensionId: 'structure', weight: 40 },
    ],
  })
  const nextState = scenarioConfigData.upsertScenarioConfigDraft(state, draft)

  assert.equal(nextState.selectedScenarioId, 'local-objection-handling')
  assert.equal(nextState.scenarios[0].title, 'Objection handling')
  assert.equal(scenarioConfigData.validateScenarioWeightTotal(nextState.scenarios[0].dimensionWeights).valid, true)
})
