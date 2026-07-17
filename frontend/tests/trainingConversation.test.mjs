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
  assert.deepEqual(payload.metadata, { scenarioTemplateId: 'new-customer-discount' })
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
    provider: 'talkwise-conversation',
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

test('buildConversationTreeMessageActionContext exposes generic conversation action endpoints', () => {
  const context = trainingConversation.buildConversationTreeMessageActionContext({
    provider: 'talkwise-conversation',
    conversationId: 42,
    messagePublicId: 'msg_leaf',
    branchId: 'branch-selected',
  })

  assert.equal(context.provider, 'talkwise-conversation')
  assert.equal(context.conversationId, '42')
  assert.equal(context.messagePublicId, 'msg_leaf')
  assert.equal(context.branchId, 'branch-selected')
  assert.deepEqual(context.availableActions, [
    'locate',
    'path',
    'children',
    'fork',
    'edit',
    'retry',
    'search',
  ])
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

test('resolveRuntimeEndpoint keeps OpenAI WebRTC on SDP endpoint', () => {
  const endpoint = trainingConversation.resolveRuntimeEndpoint({
    mode: 'realtime',
    provider: 'openai_webrtc',
    sessionId: 'training-2',
    roomId: 7,
  })

  assert.equal(
    endpoint,
    '/api/v1/training-studio/realtime/sdp?session_id=training-2&room_id=7',
  )
})

test('normalizeConversationRef rejects empty conversation ids', () => {
  assert.throws(
    () => trainingConversation.normalizeConversationRef({ provider: 'talkwise', conversationId: ' ' }),
    /conversationId cannot be empty/,
  )
})
