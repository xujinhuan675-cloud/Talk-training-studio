import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTrainingConversationModule() {
  const sourcePath = path.resolve('src/services/trainingConversation.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(
    os.tmpdir(),
    `training-conversation-${process.pid}-${Date.now()}.mjs`,
  )
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const trainingConversation = await loadTrainingConversationModule()

async function withMockFetch(handler, testBody) {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init })
    const response = handler(String(url), init)
    if (response instanceof Response) return response
    return new Response(JSON.stringify({ data: response }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    await testBody(calls)
  } finally {
    globalThis.fetch = originalFetch
  }
}

test('normalizeTrainingTurn maps TalkWise senders to training roles and preserves metadata', () => {
  const turn = trainingConversation.normalizeTrainingTurn({
    id: 17,
    sender_type: 'persona',
    sender_id: 'customer-1',
    content: 'That budget still feels risky.',
    metadata: { source: 'realtime_voice', confidence: 0.91 },
  })

  assert.equal(turn.turnId, '17')
  assert.equal(turn.role, 'assistant')
  assert.equal(turn.speaker, 'counterpart')
  assert.equal(turn.sender, 'persona')
  assert.equal(turn.senderId, 'customer-1')
  assert.equal(turn.text, 'That budget still feels risky.')
  assert.deepEqual(turn.metadata, { source: 'realtime_voice', confidence: 0.91 })
})

test('buildTrainingConversationPayload carries LibreChat-style branch fields', () => {
  const payload = trainingConversation.buildTrainingConversationPayload({
    mode: 'text',
    conversation: {
      provider: 'talkwise-stakeholder-room',
      conversationId: 42,
      legacyRoomId: 42,
      branchTailMessageId: 'msg_tail',
      metadata: { trainingSessionId: 'training-1' },
    },
    turn: {
      role: 'user',
      text: 'Can we begin with a smaller pilot?',
      parentMessageId: 'msg_parent',
      branchId: 'branch_main',
      provider: 'openai',
      model: 'gpt-test',
      model_spec: 'openai::https://openai.example/v1::responses::gpt-test',
    },
    metadata: { scenarioTemplateId: 'new-customer-discount' },
  })

  assert.equal(payload.provider, 'talkwise-stakeholder-room')
  assert.equal(payload.endpoint, '/api/v1/stakeholder/rooms/42/messages')
  assert.equal(payload.conversation.branchTailMessageId, 'msg_tail')
  assert.equal(payload.turns[0].parentMessageId, 'msg_parent')
  assert.equal(payload.turns[0].branchId, 'branch_main')
  assert.equal(payload.turns[0].provider, 'openai')
  assert.equal(payload.turns[0].model, 'gpt-test')
  assert.equal(
    payload.turns[0].modelSpec,
    'openai::https://openai.example/v1::responses::gpt-test',
  )
  assert.deepEqual(payload.metadata, { scenarioTemplateId: 'new-customer-discount' })
})

test('buildTrainingConversationPayload carries selected provider/model without rewriting training metadata', () => {
  const payload = trainingConversation.buildTrainingConversationPayload({
    mode: 'text',
    conversation: {
      provider: 'talkwise-conversation',
      conversationId: 'conversation-1',
      branchTailMessageId: 'msg-tail',
      metadata: {
        trainingSessionId: 'training-1',
        personaIds: ['buyer', 'cfo'],
        scenarioId: 9,
        dispatcher: { policy: 'stakeholder_turns' },
        evaluation: { rubricId: 'sales-v1' },
        growthReport: { reportId: 'growth-1' },
      },
    },
    turn: {
      role: 'user',
      text: 'Can we narrow the scope before talking price?',
      provider: 'openai',
      model: 'gpt-selected',
      modelSpec: 'openai::https://openai.example/v1::responses::gpt-selected',
      metadata: {
        source: 'typed_input',
        personaIds: ['turn-local-shadow'],
      },
    },
    metadata: {
      scenarioTemplateId: 'enterprise-renewal',
      personaIds: ['buyer', 'cfo'],
      evaluation: { rubricId: 'sales-v1' },
    },
  })

  assert.equal(payload.provider, 'talkwise-conversation')
  assert.equal(payload.turns[0].provider, 'openai')
  assert.equal(payload.turns[0].model, 'gpt-selected')
  assert.equal(
    payload.turns[0].modelSpec,
    'openai::https://openai.example/v1::responses::gpt-selected',
  )
  assert.deepEqual(payload.turns[0].metadata, {
    source: 'typed_input',
    personaIds: ['turn-local-shadow'],
  })
  assert.deepEqual(payload.conversation.metadata, {
    trainingSessionId: 'training-1',
    personaIds: ['buyer', 'cfo'],
    scenarioId: 9,
    dispatcher: { policy: 'stakeholder_turns' },
    evaluation: { rubricId: 'sales-v1' },
    growthReport: { reportId: 'growth-1' },
  })
  assert.deepEqual(payload.metadata, {
    scenarioTemplateId: 'enterprise-renewal',
    personaIds: ['buyer', 'cfo'],
    evaluation: { rubricId: 'sales-v1' },
  })
  assert.equal('provider' in payload.metadata, false)
  assert.equal('model' in payload.metadata, false)
})

test('buildTrainingConversationPayload keeps model registry metadata from shadowing TalkWise semantics', () => {
  const payload = trainingConversation.buildTrainingConversationPayload({
    mode: 'text',
    conversation: {
      provider: 'talkwise-conversation',
      conversationId: 'conversation-1',
      metadata: {
        trainingSessionId: 'training-1',
        personaIds: ['buyer', 'cfo'],
        scenarioId: 9,
        dispatcher: { policy: 'stakeholder_turns' },
        evaluation: { rubricId: 'sales-v1' },
        growthReport: { reportId: 'growth-1' },
        report: { id: 'full-report-1' },
        liveGuidance: { enabled: true },
      },
    },
    turn: {
      role: 'user',
      text: 'Can we narrow the scope before talking price?',
      provider: 'openai',
      model: 'gpt-selected',
      metadata: {
        model_registry: { provider: 'openai' },
        model_spec: { id: 'gpt-selected' },
        personaIds: ['turn-local-shadow'],
        scenarioId: 404,
        dispatcher: { policy: 'generic-chat' },
        evaluation: { rubricId: 'generic' },
        growthReport: { reportId: 'generic' },
        report: { id: 'generic-report' },
        liveGuidance: { enabled: false },
      },
    },
    metadata: {
      provider: 'openai',
      model: 'gpt-selected',
      model_registry: { provider: 'openai' },
      model_spec: { id: 'gpt-selected' },
      personaIds: ['payload-shadow'],
      scenarioId: 404,
      dispatcher: { policy: 'generic-chat' },
      evaluation: { rubricId: 'generic' },
      growthReport: { reportId: 'generic' },
      report: { id: 'generic-report' },
      liveGuidance: { enabled: false },
    },
  })

  assert.equal(payload.provider, 'talkwise-conversation')
  assert.equal(payload.turns[0].provider, 'openai')
  assert.equal(payload.turns[0].model, 'gpt-selected')
  assert.deepEqual(payload.conversation.metadata, {
    trainingSessionId: 'training-1',
    personaIds: ['buyer', 'cfo'],
    scenarioId: 9,
    dispatcher: { policy: 'stakeholder_turns' },
    evaluation: { rubricId: 'sales-v1' },
    growthReport: { reportId: 'growth-1' },
    report: { id: 'full-report-1' },
    liveGuidance: { enabled: true },
  })
  assert.deepEqual(payload.metadata.model_registry, { provider: 'openai' })
  assert.deepEqual(payload.metadata.model_spec, { id: 'gpt-selected' })
  assert.deepEqual(payload.turns[0].metadata.personaIds, ['turn-local-shadow'])
  assert.deepEqual(payload.metadata.personaIds, ['payload-shadow'])
})

test('resolveRuntimeEndpoint picks realtime websocket endpoint with session binding', () => {
  const endpoint = trainingConversation.resolveRuntimeEndpoint({
    mode: 'realtime',
    provider: 'pipecat',
    sessionId: 'training 1',
    roomId: 42,
  })

  assert.equal(
    endpoint,
    '/api/v1/training-studio/realtime?session_id=training+1&room_id=42&provider=pipecat',
  )
})

test('resolveRuntimeEndpoint routes message-tree provider to conversation chat endpoint', () => {
  const endpoint = trainingConversation.resolveRuntimeEndpoint({
    mode: 'text',
    provider: 'conversation_message_tree',
    conversation: {
      conversationId: 42,
    },
  })

  assert.equal(endpoint, '/api/v1/conversations/42/chat')
})

test('buildTrainingConversationPayload maps branch tail to chat parent message', () => {
  const payload = trainingConversation.buildTrainingConversationPayload({
    mode: 'text',
    conversation: {
      provider: 'talkwise-conversation',
      conversationId: 42,
      branchTailMessageId: 'msg_tail',
      metadata: { branchId: 'branch-selected' },
    },
    turn: {
      role: 'user',
      text: 'Continue from the selected answer.',
    },
  })

  assert.equal(payload.endpoint, '/api/v1/conversations/42/chat')
  assert.equal(payload.turns[0].parentMessageId, 'msg_tail')
  assert.equal(payload.turns[0].branchId, 'branch-selected')
})

test('buildConversationTreeMessageActionContext exposes controlled conversation action endpoints', () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'conversation_tree',
    conversationId: 42,
    messagePublicId: 'msg_leaf',
    branchId: 'branch-selected',
  })

  assert.equal(context.provider, 'conversation_tree')
  assert.equal(context.conversationId, '42')
  assert.equal(context.messagePublicId, 'msg_leaf')
  assert.equal(context.branchId, 'branch-selected')
  assert.deepEqual(context.availableActions, [
    'branch',
    'locate',
    'path',
    'children',
    'search',
    'edit',
    'retry',
    'fork',
  ])
  assert.equal(context.endpoints.actions, '/api/v1/conversations/42/messages/msg_leaf/actions')
  assert.equal(context.endpoints.locate, '/api/v1/conversations/42/messages/msg_leaf/locate')
  assert.equal(context.endpoints.path, '/api/v1/conversations/42/messages/msg_leaf/path')
  assert.equal(context.endpoints.children, '/api/v1/conversations/42/messages/msg_leaf/children')
  assert.equal(context.endpoints.fork, '/api/v1/conversations/42/messages/msg_leaf/fork')
  assert.equal(context.endpoints.edit, '/api/v1/conversations/42/messages/msg_leaf/edit')
  assert.equal(context.endpoints.retry, '/api/v1/conversations/42/messages/msg_leaf/retry')
  assert.equal(context.endpoints.search, '/api/v1/conversations/42/messages/search')
})

test('buildConversationTreeMessageActionContext reads nested training metadata refs', () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    metadata: {
      conversation: {
        provider: 'message-tree',
        conversation_id: 'conv 9',
        branch_tail_message_id: 'msg_tail',
        branch_id: 'branch-from-metadata',
      },
    },
  })

  assert.equal(context.provider, 'message-tree')
  assert.equal(context.conversationId, 'conv 9')
  assert.equal(context.messagePublicId, 'msg_tail')
  assert.equal(context.branchId, 'branch-from-metadata')
  assert.equal(context.endpoints.path, '/api/v1/conversations/conv%209/messages/msg_tail/path')
})

test('buildConversationTreeMessageActionContext ignores stakeholder room local message ids', () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'talkwise-conversation',
    conversationId: 42,
    messagePublicId: 17,
  })

  assert.equal(context, null)
})

test('applyConversationTreeMessageAction posts branch payload to unified action endpoint', async () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'talkwise-conversation',
    conversationId: 7,
    messagePublicId: 'msg_selected',
  })

  await withMockFetch(
    (url, init) => {
      assert.equal(url, '/api/v1/conversations/7/messages/msg_selected/actions')
      assert.equal(init.method, 'POST')
      assert.equal(init.headers['Content-Type'], 'application/json')
      assert.deepEqual(JSON.parse(init.body), {
        action: 'branch',
        metadata: { source: 'training_room' },
        include_deleted: true,
        statuses: ['active', 'superseded'],
      })
      return {
        action: 'branch',
        message: {
          id: 2,
          conversation_id: 7,
          role: 'assistant',
          content: 'Selected branch',
          public_id: 'msg_selected',
          branch_id: 'main',
          status: 'active',
          created_at: '2026-07-17T00:01:00Z',
        },
        path: [],
        children: [],
        siblings: [],
        branch_id: 'main',
      }
    },
    async () => {
      const result = await trainingConversation.applyConversationTreeMessageAction(context, {
        action: 'branch',
        includeDeleted: true,
        statuses: [' active ', '', 'superseded'],
        metadata: { source: 'training_room' },
      })

      assert.equal(result.action, 'branch')
      assert.equal(result.message.publicId, 'msg_selected')
      assert.equal(result.branchId, 'main')
    },
  )
})

test('applyConversationTreeMessageAction supports edit and retry write payloads', async () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'talkwise-conversation',
    conversationId: 7,
    messagePublicId: 'msg_answer',
  })

  const expectedBodies = [
    {
      action: 'edit',
      content: 'Edited answer',
      metadata: { source: 'message_tree_panel' },
    },
    {
      action: 'retry',
      content: '',
      metadata: { source: 'message_tree_panel' },
    },
  ]

  await withMockFetch(
    (url, init) => {
      assert.equal(url, '/api/v1/conversations/7/messages/msg_answer/actions')
      const expected = expectedBodies.shift()
      assert.deepEqual(JSON.parse(init.body), expected)
      return {
        action: expected.action,
        message: {
          id: expected.action === 'edit' ? 3 : 4,
          conversation_id: 7,
          role: 'assistant',
          content: expected.action === 'edit' ? 'Edited answer' : '',
          public_id: expected.action === 'edit' ? 'msg_edit' : 'msg_retry',
          parent_message_id: 'msg_parent',
          branch_id: expected.action === 'edit' ? 'branch_edit' : 'branch_retry',
          status: 'active',
          created_at: '2026-07-17T00:02:00Z',
        },
        path: [],
        children: [],
        siblings: [],
        branch_id: expected.action === 'edit' ? 'branch_edit' : 'branch_retry',
      }
    },
    async () => {
      const editResult = await trainingConversation.applyConversationTreeMessageAction(context, {
        action: 'edit',
        content: ' Edited answer ',
        metadata: { source: 'message_tree_panel' },
      })
      const retryResult = await trainingConversation.applyConversationTreeMessageAction(context, {
        action: 'retry',
        metadata: { source: 'message_tree_panel' },
      })

      assert.equal(editResult.message.publicId, 'msg_edit')
      assert.equal(editResult.branchId, 'branch_edit')
      assert.equal(retryResult.message.publicId, 'msg_retry')
      assert.equal(retryResult.message.content, '')
      assert.equal(expectedBodies.length, 0)
    },
  )
})

test('applyConversationTreeMessageAction normalizes fork action result', async () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'talkwise-conversation',
    conversationId: 7,
    messagePublicId: 'msg_selected',
  })

  await withMockFetch(
    (url, init) => {
      assert.equal(url, '/api/v1/conversations/7/messages/msg_selected/actions')
      assert.deepEqual(JSON.parse(init.body), {
        action: 'fork',
        metadata: { source: 'message_tree_panel' },
        title: 'Forked path',
        option: 'includeBranches',
        include_deleted: false,
        statuses: ['active'],
      })
      return {
        action: 'fork',
        message: {
          id: 21,
          conversation_id: 8,
          role: 'assistant',
          content: 'Forked selected answer',
          public_id: 'msg_forked',
          branch_id: 'main',
          status: 'active',
          created_at: '2026-07-17T00:03:00Z',
        },
        path: [],
        children: [],
        siblings: [],
        branch_id: 'main',
        conversation: {
          id: 8,
          title: 'Forked path',
          system_prompt: null,
          model: null,
          status: 'active',
          metadata: { source: 'message_tree_panel' },
          created_at: '2026-07-17T00:03:00Z',
          updated_at: '2026-07-17T00:03:00Z',
        },
        messages: [
          {
            id: 21,
            conversation_id: 8,
            role: 'assistant',
            content: 'Forked selected answer',
            public_id: 'msg_forked',
            branch_id: 'main',
            status: 'active',
            created_at: '2026-07-17T00:03:00Z',
          },
        ],
        source_to_forked_id: { msg_selected: 'msg_forked' },
      }
    },
    async () => {
      const result = await trainingConversation.applyConversationTreeMessageAction(context, {
        action: 'fork',
        title: ' Forked path ',
        option: 'includeBranches',
        includeDeleted: false,
        statuses: ['active'],
        metadata: { source: 'message_tree_panel' },
      })

      assert.equal(result.action, 'fork')
      assert.equal(result.message.publicId, 'msg_forked')
      assert.equal(result.conversation.id, '8')
      assert.equal(result.conversation.title, 'Forked path')
      assert.deepEqual(result.sourceToForkedId, { msg_selected: 'msg_forked' })
      assert.deepEqual(result.messages.map((item) => item.publicId), ['msg_forked'])
    },
  )
})

test('applyConversationTreeMessageAction preserves server error detail with status fallback', async () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'talkwise-conversation',
    conversationId: 7,
    messagePublicId: 'msg_selected',
  })

  await withMockFetch(
    (url, init) => {
      assert.equal(url, '/api/v1/conversations/7/messages/msg_selected/actions')
      assert.equal(init.method, 'POST')
      assert.deepEqual(JSON.parse(init.body), {
        action: 'edit',
        content: 'Edited answer',
        metadata: { source: 'message_tree_panel' },
      })
      return new Response(JSON.stringify({
        error: { message: 'selected path is stale; reload before editing' },
      }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      })
    },
    async () => {
      await assert.rejects(
        () => trainingConversation.applyConversationTreeMessageAction(context, {
          action: 'edit',
          content: ' Edited answer ',
          metadata: { source: 'message_tree_panel' },
        }),
        /Failed to apply conversation tree action: 409 - selected path is stale; reload before editing/,
      )
    },
  )
})

test('getMessageActionResultPath prefers returned path and rebuilds message fallbacks', () => {
  const root = {
    publicId: 'msg_root',
    parentMessageId: null,
    content: 'Root',
  }
  const selected = {
    publicId: 'msg_selected',
    parentMessageId: 'msg_root',
    content: 'Selected',
  }
  const sibling = {
    publicId: 'msg_sibling',
    parentMessageId: 'msg_root',
    content: 'Sibling',
  }

  assert.deepEqual(
    trainingConversation.getMessageActionResultPath({
      message: selected,
      path: [root, selected],
      messages: [sibling],
    }).map((message) => message.publicId),
    ['msg_root', 'msg_selected'],
  )

  assert.deepEqual(
    trainingConversation.getMessageActionResultPath({
      message: selected,
      path: [],
      messages: [sibling, selected, root],
    }).map((message) => message.publicId),
    ['msg_root', 'msg_selected'],
  )

  assert.deepEqual(
    trainingConversation.getMessageActionResultPath({
      message: selected,
      path: [],
      messages: [],
    }).map((message) => message.publicId),
    ['msg_selected'],
  )
})

test('fetchConversationTreeMessagePath normalizes readonly path messages', async () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'talkwise-conversation',
    conversationId: 42,
    messagePublicId: 'msg_leaf',
  })

  await withMockFetch(
    (url) => {
      assert.equal(
        url,
        '/api/v1/conversations/42/messages/msg_leaf/path?limit=3&include_deleted=true&statuses=active&statuses=superseded',
      )
      return [
        {
          id: 1,
          conversation_id: 42,
          role: 'user',
          content: 'Root turn',
          public_id: 'msg_root',
          branch_id: 'main',
          status: 'active',
          created_at: '2026-07-17T00:00:00Z',
        },
        {
          id: 2,
          conversation_id: 42,
          role: 'assistant',
          content: 'Leaf answer',
          public_id: 'msg_leaf',
          parent_message_id: 'msg_root',
          branch_id: 'main',
          status: 'superseded',
          provider: 'openai',
          model: 'gpt-test',
          metadata: { score: 1 },
          created_at: '2026-07-17T00:01:00Z',
        },
      ]
    },
    async () => {
      const pathItems = await trainingConversation.fetchConversationTreeMessagePath(context, {
        limit: 3,
        includeDeleted: true,
        statuses: ['active', ' ', 'superseded'],
      })

      assert.deepEqual(pathItems.map((item) => item.publicId), ['msg_root', 'msg_leaf'])
      assert.equal(pathItems[1].parentMessageId, 'msg_root')
      assert.equal(pathItems[1].branchId, 'main')
      assert.equal(pathItems[1].status, 'superseded')
      assert.equal(pathItems[1].provider, 'openai')
      assert.deepEqual(pathItems[1].metadata, { score: 1 })
    },
  )
})

test('fetchConversationTreeBranchSnapshot loads focused node children and search results', async () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'talkwise-conversation',
    conversationId: 7,
    messagePublicId: 'msg_selected',
    branchId: 'main',
  })

  await withMockFetch(
    (url) => {
      if (url === '/api/v1/conversations/7/messages/msg_selected/locate?before=2&after=2') {
        return {
          message: {
            id: 2,
            conversation_id: 7,
            role: 'assistant',
            content: 'Selected answer',
            public_id: 'msg_selected',
            parent_message_id: 'msg_root',
            branch_id: 'main',
            status: 'active',
            created_at: '2026-07-17T00:01:00Z',
          },
          path: [
            {
              id: 1,
              conversation_id: 7,
              role: 'user',
              content: 'Root question',
              public_id: 'msg_root',
              branch_id: 'main',
              status: 'active',
              created_at: '2026-07-17T00:00:00Z',
            },
            {
              id: 2,
              conversation_id: 7,
              role: 'assistant',
              content: 'Selected answer',
              public_id: 'msg_selected',
              parent_message_id: 'msg_root',
              branch_id: 'main',
              status: 'active',
              created_at: '2026-07-17T00:01:00Z',
            },
          ],
          context: [],
        }
      }
      if (url === '/api/v1/conversations/7/messages/msg_selected/children') {
        return [
          {
            id: 3,
            conversation_id: 7,
            role: 'user',
            content: 'Main follow-up',
            public_id: 'msg_child_main',
            parent_message_id: 'msg_selected',
            branch_id: 'main',
            status: 'active',
            created_at: '2026-07-17T00:02:00Z',
          },
          {
            id: 4,
            conversation_id: 7,
            role: 'user',
            content: 'Alternate follow-up',
            public_id: 'msg_child_alt',
            parent_message_id: 'msg_selected',
            branch_id: 'branch_alt',
            status: 'active',
            created_at: '2026-07-17T00:03:00Z',
          },
        ]
      }
      if (url === '/api/v1/conversations/7/messages/search?q=pilot&limit=8&include_path=true&context_before=1&context_after=1&branch_id=main') {
        return [
          {
            message: {
              id: 5,
              conversation_id: 7,
              role: 'assistant',
              content: 'Pilot discussion',
              public_id: 'msg_search',
              parent_message_id: 'msg_child_main',
              branch_id: 'main',
              status: 'active',
              created_at: '2026-07-17T00:04:00Z',
            },
            path: [],
            context: [],
          },
        ]
      }
      throw new Error(`Unexpected URL ${url}`)
    },
    async (calls) => {
      const snapshot = await trainingConversation.fetchConversationTreeBranchSnapshot(context, {
        branchId: 'main',
        searchQuery: 'pilot',
      })

      assert.deepEqual(
        calls.map((call) => call.url).sort(),
        [
          '/api/v1/conversations/7/messages/msg_selected/children',
          '/api/v1/conversations/7/messages/msg_selected/locate?before=2&after=2',
          '/api/v1/conversations/7/messages/search?q=pilot&limit=8&include_path=true&context_before=1&context_after=1&branch_id=main',
        ].sort(),
      )
      assert.equal(snapshot.message.publicId, 'msg_selected')
      assert.deepEqual(snapshot.path.map((item) => item.publicId), ['msg_root', 'msg_selected'])
      assert.deepEqual(snapshot.children.map((item) => item.branchId), ['main', 'branch_alt'])
      assert.equal(snapshot.searchResults[0].message.publicId, 'msg_search')
    },
  )
})

test('resolveRuntimeEndpoint maps legacy OpenAI WebRTC aliases to Pipecat websocket endpoint', () => {
  const endpoint = trainingConversation.resolveRuntimeEndpoint({
    mode: 'realtime',
    provider: 'openai_webrtc',
    sessionId: 'training-2',
    roomId: 7,
  })

  assert.equal(
    endpoint,
    '/api/v1/training-studio/realtime?session_id=training-2&room_id=7&provider=pipecat',
  )
})

test('normalizeConversationRef rejects empty conversation ids', () => {
  assert.throws(
    () => trainingConversation.normalizeConversationRef({ provider: 'talkwise', conversationId: ' ' }),
    /conversationId cannot be empty/,
  )
})
