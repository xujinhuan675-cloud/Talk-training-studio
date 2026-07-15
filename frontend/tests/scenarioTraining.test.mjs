import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTsModule(sourcePath, prefix) {
  const source = fs.readFileSync(path.resolve(sourcePath), 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `${prefix}-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const scenarioTrainingService = await loadTsModule('src/services/scenarioTraining.ts', 'scenario-training-service')
const scenarioTrainingData = await loadTsModule('src/data/trainingScenarios.ts', 'scenario-training-data')

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
            training_points: ['快速建立信任'],
          },
        ],
      }),
    }
  }

  const result = await scenarioTrainingService.fetchScenarioTrainingCatalog()

  assert.equal(calls[0].url, '/api/v1/training-studio/scenario-templates')
  assert.deepEqual(calls[0].init, {})
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
    },
  })
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

  assert.equal(serviceConfig.category, 'workplace')
  assert.equal(expertConfig.difficulty, 'hard')
  assert.equal(expertConfig.category, 'negotiation')
  assert.equal(expertConfig.metadata.source, 'scenario_training')
  assert.equal(expertConfig.metadata.scenario_training.id, expertScenario.id)
})

test('scenario prompts carry realistic customer simulation rules', () => {
  const scenario = scenarioTrainingData.scenarioTrainingCatalog.find(
    (item) => item.id === 'new-customer-discount',
  )

  assert.ok(scenario)

  const prompt = scenarioTrainingData.buildScenarioTrainingPrompt(scenario, 'text')
  const payload = scenarioTrainingData.buildScenarioTrainingBattlePayload(scenario, 'text')

  assert.match(prompt, /not a cooperative demo/)
  assert.match(prompt, /30-120 Chinese characters/)
  assert.match(prompt, /Do not reveal all needs, budget, objections, or bottom lines at once/)
  assert.match(prompt, /never score the learner/)
  assert.match(prompt, /Difficulty behavior:/)
  assert.match(payload.persona_style, /Speak like a real counterpart/)
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
  })
})
