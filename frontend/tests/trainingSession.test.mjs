import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTrainingSessionModule() {
  const sourcePath = path.resolve('src/services/trainingSession.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  let outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(os.tmpdir(), `training-session-${process.pid}-${Date.now()}.mjs`)
  const cleanupPaths = [outputPath]
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
  if (outputText.includes("from '../utils/errors'")) {
    const errorsSource = fs.readFileSync(path.resolve('src/utils/errors.ts'), 'utf8')
    const errorsOutput = ts.transpileModule(errorsSource, {
      compilerOptions: {
        module: ts.ModuleKind.ES2022,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText
    const errorsPath = path.join(os.tmpdir(), `errors-utils-${process.pid}-${Date.now()}.mjs`)
    fs.writeFileSync(errorsPath, errorsOutput)
    cleanupPaths.push(errorsPath)
    outputText = outputText.replace(
      "from '../utils/errors'",
      `from '${pathToFileURL(errorsPath).href}'`,
    )
  }
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    cleanupPaths.forEach((item) => fs.rmSync(item, { force: true }))
  }
}

const trainingSession = await loadTrainingSessionModule()
const expectedAuthHeaders = {
  'X-Mock-User': 'admin',
  'X-User-Id': 'user-admin-001',
  'X-System-Role': 'admin',
  'X-Team-Id': 'team-ops',
}

function installFetchStub(data = { session_id: 'session-1', mode: 'voice', status: 'created' }) {
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({ code: 0, message: 'ok', data }),
    }
  }
  return calls
}

test('createTrainingSession posts to the sessions collection with JSON body', async () => {
  const calls = installFetchStub()
  const body = {
    mode: 'voice',
    scenario_template_id: 'new-customer-discount',
    user_id: 'user-sales-001',
    team_id: 'team-revenue',
    task_config: {
      role: 'Sales Associate',
      level: 'Senior',
      tech_stack: ['discovery'],
      question_type_ratios: { behavioral: 30, craft: 50, pressure: 20 },
      question_count: 5,
      framework: 'prep',
      difficulty: 'medium',
      category: 'sales',
      metadata: {
        source: 'scenario_training',
        scenario_training: { id: 'new-customer-discount' },
      },
    },
  }

  await trainingSession.createTrainingSession(body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(calls[0].init.headers, { ...expectedAuthHeaders, 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
})

test('startTrainingSession posts to the start endpoint with JSON body', async () => {
  const calls = installFetchStub()
  const body = { room_id: 42, room_type: 'battle_prep' }

  await trainingSession.startTrainingSession('session-1', body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session-1/start')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
})

test('completeTrainingSession posts to the complete endpoint with JSON body', async () => {
  const calls = installFetchStub()
  const body = { report_id: 501, generate_report: false }

  await trainingSession.completeTrainingSession('session-1', body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session-1/complete')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
})

test('completeTrainingSession posts an empty JSON body by default', async () => {
  const calls = installFetchStub()

  await trainingSession.completeTrainingSession('session-1')

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session-1/complete')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(calls[0].init.headers, { ...expectedAuthHeaders, 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(calls[0].init.body), {})
})

test('completeTrainingSession can persist message tree branch metadata', async () => {
  const calls = installFetchStub()
  const metadata = trainingSession.buildTrainingCompletionBranchMetadata({
    provider: 'talkwise-conversation',
    conversationId: '7',
    selectedMessageId: 'msg-tail',
    branchId: 'branch-review',
    sourceMessageId: 99,
    path: [
      {
        publicId: 'msg-root',
        role: 'user',
        content: 'Can we revisit pricing?',
        branchId: 'main',
        parentMessageId: null,
      },
      {
        publicId: 'msg-tail',
        role: 'assistant',
        content: 'Use a pilot with a measurable success bar.',
        branchId: 'branch-review',
        parentMessageId: 'msg-root',
      },
    ],
  })

  await trainingSession.completeTrainingSession('session-1', {
    generate_report: false,
    metadata,
  })

  const body = JSON.parse(calls[0].init.body)
  assert.equal(body.generate_report, false)
  assert.equal(body.metadata.messageTreeSelection.provider, 'talkwise-conversation')
  assert.equal(body.metadata.messageTreeSelection.selectedMessageId, 'msg-tail')
  assert.equal(body.metadata.messageTreeSelection.forkPointMessageId, 'msg-root')
  assert.equal(body.metadata.messageTreeSelection.affectsScoring, false)
  assert.equal(body.metadata.selectedPath.affectsCompletion, false)
  assert.deepEqual(body.metadata.selectedPath.messageIds, ['msg-root', 'msg-tail'])
})

test('training session requests surface FastAPI detail string errors', async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 409,
    json: async () => ({ detail: 'training session already completed' }),
  })

  await assert.rejects(
    trainingSession.completeTrainingSession('session-1'),
    /training session already completed/,
  )
})

test('training session requests explain backend proxy failures', async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 502,
    json: async () => {
      throw new Error('proxy response is not JSON')
    },
  })

  await assert.rejects(
    trainingSession.createTrainingSession({
      mode: 'voice',
      task_config: {
        role: 'Sales Associate',
        level: 'Senior',
        tech_stack: ['discovery'],
        question_type_ratios: { behavioral: 30, craft: 50, pressure: 20 },
        question_count: 5,
        framework: 'prep',
        difficulty: 'medium',
        category: 'sales',
      },
    }),
    /backend service unavailable/,
  )
})

test('requestTrainingGuidance posts guidance context and returns response data', async () => {
  const data = {
    session_id: 'session 1',
    events: [
      {
        event_type: 'coaching_tip',
        severity: 'info',
        title: 'Ask a follow-up',
        message: 'Probe for measurable impact.',
        suggested_text: 'Can you share the result in numbers?',
        metadata: { rubric_key: 'impact' },
        created_at: '2026-07-14T08:00:00Z',
      },
    ],
  }
  const calls = installFetchStub(data)
  const body = {
    task_goal: 'Practice discovery calls',
    rubric: { impact: 0.4, clarity: 0.6 },
    recent_turns: [
      {
        speaker: 'candidate',
        text: 'I improved conversion.',
        turn_id: 'turn-1',
        metadata: {
          source: 'live_coach_text_input',
          trainingProfile: 'live_coach',
          translation: {
            mode: 'text_first_mvp',
            sourceLanguage: 'zh-CN',
            targetLanguage: 'en-US',
            preserveTone: true,
          },
        },
      },
      { speaker: 'coach', text: 'What changed after that?' },
    ],
  }

  const result = await trainingSession.requestTrainingGuidance('session 1', body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session%201/guidance')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(calls[0].init.headers, { ...expectedAuthHeaders, 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
  assert.deepEqual(result, data)
})

test('getTrainingGuidanceStreamUrl builds an EventSource endpoint', () => {
  const url = trainingSession.getTrainingGuidanceStreamUrl('session 1', {
    message_limit: 25,
    poll_interval_ms: 750,
  })

  assert.equal(
    url,
    '/api/v1/training-studio/sessions/session%201/guidance/stream?mock_user=admin&message_limit=25&poll_interval_ms=750',
  )
})

test('getTrainingConversationBranchInfo extracts selected path metadata from a session', () => {
  const info = trainingSession.getTrainingConversationBranchInfo({
    session: {
      task_config: {
        metadata: {
          messageTreeSelection: {
            provider: 'talkwise-conversation',
            conversationId: 'conv-1',
            selectedMessageId: 'msg-leaf',
            branchId: 'branch-main',
            path: [
              { publicId: 'msg-root', role: 'system', content: 'Start here' },
              { public_id: 'msg-leaf', role: 'assistant', text: 'Selected answer', branch_id: 'branch-main' },
            ],
          },
        },
      },
    },
  })

  assert.equal(info.source, 'session')
  assert.equal(info.sourceDetail, 'session.task_config.metadata')
  assert.equal(info.provider, 'talkwise-conversation')
  assert.equal(info.conversationId, 'conv-1')
  assert.equal(info.branchId, 'branch-main')
  assert.equal(info.selectedTailMessageId, 'msg-leaf')
  assert.equal(info.pathCount, 2)
  assert.equal(info.pathTextState, 'with_text')
  assert.deepEqual(info.selectedPath.map((item) => item.publicId), ['msg-root', 'msg-leaf'])
  assert.match(info.pathSummary, /Selected answer/)
  assert.equal(info.lastReplyPreview, 'Selected answer')
})

test('buildTrainingCompletionBranchMetadata serializes selected path as replay-only metadata', () => {
  const metadata = trainingSession.buildTrainingCompletionBranchMetadata({
    provider: 'talkwise-conversation',
    conversationId: 'conv-branch',
    selectedMessageId: 'msg-leaf',
    branchId: 'branch-review',
    path: [
      { publicId: 'msg-root', role: 'user', content: 'Can we revisit pricing?', branchId: 'main' },
      { publicId: 'msg-leaf', role: 'assistant', content: 'Frame it as a pilot.', branchId: 'branch-review' },
    ],
  })

  const info = trainingSession.getTrainingConversationBranchInfo({
    session: {
      task_config: {
        metadata,
      },
    },
  })

  assert.equal(metadata.messageTreeSelection.purpose, 'training_replay_context')
  assert.equal(metadata.messageTreeSelection.replayContextOnly, true)
  assert.equal(metadata.messageTreeSelection.affectsScoring, false)
  assert.equal(metadata.messageTreeSelection.affectsCompletion, false)
  assert.equal(info.source, 'session')
  assert.equal(info.sourceDetail, 'session.task_config.metadata')
  assert.equal(info.branchId, 'branch-review')
  assert.equal(info.selectedTailMessageId, 'msg-leaf')
  assert.equal(info.forkPointMessageId, 'msg-root')
  assert.equal(info.lastReplyPreview, 'Frame it as a pilot.')
})

test('getTrainingConversationBranchInfo extracts id-only selected path state without inventing text', () => {
  const info = trainingSession.getTrainingConversationBranchInfo({
    session: {
      metadata: {
        runtime: 'conversation_message_tree',
        branchId: 'main',
        selectedPath: {
          branchId: 'main',
          tailMessageId: 'msg-tail',
          messageIds: ['msg-root', 'msg-tail'],
          purpose: 'training_replay_context',
          replayContextOnly: true,
        },
        currentBranchTail: {
          branchId: 'main',
          messageId: 'msg-tail',
        },
      },
    },
  })

  assert.equal(info.source, 'session')
  assert.equal(info.sourceDetail, 'session.metadata')
  assert.equal(info.branchId, 'main')
  assert.equal(info.selectedTailMessageId, 'msg-tail')
  assert.equal(info.pathCount, 2)
  assert.equal(info.pathTextState, 'id_only')
  assert.deepEqual(info.selectedPath.map((item) => item.publicId), ['msg-root', 'msg-tail'])
  assert.equal(info.pathSummary, undefined)
  assert.equal(info.lastReplyPreview, undefined)
})

test('getTrainingConversationBranchInfo reads fork point and last reply preview', () => {
  const info = trainingSession.getTrainingConversationBranchInfo({
    session: {
      task_config: {
        metadata: {
          messageTreeSelection: {
            provider: 'talkwise-conversation',
            conversationId: 'conv-branch',
            branchId: 'branch-review',
            forked_from_message_id: 'msg-objection',
            path: [
              { publicId: 'msg-root', role: 'user', content: 'Can we revisit pricing?' },
              { publicId: 'msg-objection', role: 'assistant', content: 'We can talk through value first.' },
              {
                publicId: 'msg-leaf',
                role: 'assistant',
                content: 'I can propose an annual pilot with a measurable success bar.',
                branchId: 'branch-review',
                parentMessageId: 'msg-objection',
              },
            ],
          },
        },
      },
    },
  })

  assert.equal(info.branchId, 'branch-review')
  assert.equal(info.selectedTailMessageId, 'msg-leaf')
  assert.equal(info.forkPointMessageId, 'msg-objection')
  assert.equal(info.lastReplyPreview, 'I can propose an annual pilot with a measurable success bar.')
})

test('getTrainingConversationBranchInfo hides default main branch when no path is selected', () => {
  const info = trainingSession.getTrainingConversationBranchInfo({
    session: {
      metadata: {
        runtime: 'conversation_message_tree',
        branchId: 'main',
        selectedPath: {
          branchId: 'main',
          tailMessageId: null,
          messageIds: [],
        },
        currentBranchTail: {
          branchId: 'main',
          messageId: null,
        },
      },
    },
  })

  assert.equal(info, null)
})

test('getTrainingConversationBranchInfo reads report and progress branch metadata fallbacks', () => {
  const reportInfo = trainingSession.getTrainingConversationBranchInfo({
    report: {
      content: {},
      metadata: {
        conversationTree: {
          conversation_id: 'conv-report',
          branch_tail_message_id: 'msg-report-tail',
          branch_id: 'branch-report',
          path_count: 4,
          path_summary: 'Root / Objection / Selected close',
        },
      },
    },
  })
  const progressInfo = trainingSession.getTrainingConversationBranchInfo({
    progress: {
      metadata: {
        conversation_ref: {
          provider: 'message-tree',
          conversation_id: 'conv-progress',
          branch_tail_message_id: 'msg-progress-tail',
          branch_id: 'branch-progress',
        },
      },
    },
  })

  assert.equal(reportInfo.source, 'report')
  assert.equal(reportInfo.sourceDetail, 'report.metadata')
  assert.equal(reportInfo.conversationId, 'conv-report')
  assert.equal(reportInfo.selectedTailMessageId, 'msg-report-tail')
  assert.equal(reportInfo.pathCount, 4)
  assert.equal(reportInfo.pathTextState, 'reference_only')
  assert.equal(reportInfo.pathSummary, 'Root / Objection / Selected close')
  assert.equal(progressInfo.source, 'progress')
  assert.equal(progressInfo.sourceDetail, 'progress.metadata')
  assert.equal(progressInfo.provider, 'message-tree')
  assert.equal(progressInfo.branchId, 'branch-progress')
  assert.equal(progressInfo.pathTextState, 'reference_only')
})

test('getTrainingConversationBranchInfo keeps source priority and report content metadata detail', () => {
  const info = trainingSession.getTrainingConversationBranchInfo({
    session: {
      metadata: {
        messageTreeSelection: {
          conversationId: 'conv-session',
          branchId: 'branch-session',
          tailMessageId: 'msg-session-tail',
        },
      },
    },
    report: {
      metadata: {
        conversationTree: {
          conversation_id: 'conv-report',
          branch_id: 'branch-report',
          branch_tail_message_id: 'msg-report-tail',
        },
      },
      content: {
        metadata: {
          conversationTree: {
            conversation_id: 'conv-report-content',
            branch_id: 'branch-report-content',
            branch_tail_message_id: 'msg-report-content-tail',
          },
        },
      },
    },
  })
  const reportContentInfo = trainingSession.getTrainingConversationBranchInfo({
    report: {
      content: {
        metadata: {
          conversationTree: {
            conversation_id: 'conv-report-content',
            branch_id: 'branch-report-content',
            branch_tail_message_id: 'msg-report-content-tail',
          },
        },
      },
    },
  })

  assert.equal(info.source, 'session')
  assert.equal(info.sourceDetail, 'session.metadata')
  assert.equal(info.conversationId, 'conv-session')
  assert.equal(info.branchId, 'branch-session')
  assert.equal(reportContentInfo.source, 'report')
  assert.equal(reportContentInfo.sourceDetail, 'report.content.metadata')
  assert.equal(reportContentInfo.conversationId, 'conv-report-content')
  assert.equal(reportContentInfo.pathTextState, 'reference_only')
})

test('getTrainingConversationBranchInfo hides when metadata has no branch context', () => {
  const info = trainingSession.getTrainingConversationBranchInfo({
    session: {
      task_config: {
        metadata: {
          source: 'scenario_training',
          scenario_training: { id: 'new-customer-discount' },
        },
      },
    },
    report: {
      summary: 'Report summary',
      content: {
        communication_suggestions: [{ suggestion: 'Ask a follow-up question.' }],
      },
    },
  })

  assert.equal(info, null)
})

test('persistTrainingGuidanceEvents posts structured coach events', async () => {
  const data = {
    batch_id: 'batch-1',
    saved_count: 1,
    messages: [],
  }
  const calls = installFetchStub(data)
  const body = {
    reason: 'session_complete',
    source: 'client',
    window_size: 2,
    total_turn_count: 2,
    events: [
      {
        event_type: 'risk',
        severity: 'warning',
        title: 'Objection surfaced',
        message: 'The counterpart signaled resistance.',
        suggested_text: 'That concern makes sense.',
        metadata: { risk_type: 'objection' },
      },
    ],
    metadata: {
      trainingProfile: 'live_coach',
      sourceLanguage: 'zh-CN',
      targetLanguage: 'en-US',
    },
  }

  const result = await trainingSession.persistTrainingGuidanceEvents('session 1', body)

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session%201/guidance-events')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(calls[0].init.headers, { ...expectedAuthHeaders, 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(calls[0].init.body), body)
  assert.deepEqual(result, data)
})

test('getTrainingSession and report use GET endpoints without request init', async () => {
  const calls = installFetchStub()

  await trainingSession.getTrainingSession('session 1')
  await trainingSession.getTrainingSessionReport('session-1')

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions/session%201')
  assert.deepEqual(calls[0].init, { headers: expectedAuthHeaders })
  assert.equal(calls[1].url, '/api/v1/training-studio/sessions/session-1/report')
  assert.deepEqual(calls[1].init, { headers: expectedAuthHeaders })
})

test('getTrainingSession preserves failed status failure reason from backend', async () => {
  installFetchStub({
    session_id: 'session-failed',
    mode: 'voice',
    status: 'failed',
    task_config: {
      role: 'Sales Associate',
      level: 'Senior',
      tech_stack: ['discovery'],
      question_type_ratios: { behavioral: 30, craft: 50, pressure: 20 },
      question_count: 5,
      framework: 'prep',
      difficulty: 'medium',
      category: 'sales',
    },
    message_count: 4,
    failure_reason: 'report generation timed out',
  })

  const result = await trainingSession.getTrainingSession('session-failed')

  assert.equal(result.status, 'failed')
  assert.equal(result.failure_reason, 'report generation timed out')
})

test('listTrainingSessions uses the sessions collection endpoint', async () => {
  const calls = installFetchStub([])

  await trainingSession.listTrainingSessions()

  assert.equal(calls[0].url, '/api/v1/training-studio/sessions')
  assert.deepEqual(calls[0].init, { headers: expectedAuthHeaders })
})

test('listTrainingSessions appends optional filters', async () => {
  const calls = installFetchStub([])

  await trainingSession.listTrainingSessions({
    skip: 10,
    limit: 20,
    userId: 'user-sales-001',
    teamId: 'team-revenue',
    scenarioTemplateId: 'enterprise-demo-objection',
  })

  assert.equal(
    calls[0].url,
    '/api/v1/training-studio/sessions?skip=10&limit=20&user_id=user-sales-001&team_id=team-revenue&scenario_template_id=enterprise-demo-objection',
  )
  assert.deepEqual(calls[0].init, { headers: expectedAuthHeaders })
})
