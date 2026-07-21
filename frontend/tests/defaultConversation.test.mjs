import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

function createRoom(overrides) {
  return {
    id: 1,
    name: 'Room',
    type: 'private',
    persona_ids: ['persona-1'],
    scenario_id: null,
    created_at: '2026-01-01T00:00:00.000Z',
    last_message_at: null,
    ...overrides,
  }
}

async function loadDefaultConversationModule(mockState) {
  const mockId = `__defaultConversationMock_${randomUUID().replaceAll('-', '')}`
  globalThis[mockId] = mockState

  const mockApiPath = path.join(os.tmpdir(), `default-conversation-api-${mockId}.mjs`)
  fs.writeFileSync(mockApiPath, `
    const mock = globalThis['${mockId}']

    export async function fetchRooms() {
      mock.calls.fetchRooms += 1
      return mock.rooms
    }

    export async function createPersona(data) {
      mock.calls.createPersonas.push(data)
    }

    export async function createRoom(data) {
      mock.calls.createRooms.push(data)
      return mock.createdRoom
    }
  `)

  const source = fs.readFileSync(path.resolve('src/services/defaultConversation.ts'), 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })

  const outputPath = path.join(os.tmpdir(), `default-conversation-${mockId}.mjs`)
  const outputText = output.outputText.replace(
    /from\s+['"]\.\/api['"]/,
    `from '${pathToFileURL(mockApiPath).href}'`,
  )
  fs.writeFileSync(outputPath, outputText)

  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(mockApiPath, { force: true })
    fs.rmSync(outputPath, { force: true })
    delete globalThis[mockId]
  }
}

function createMockState(overrides = {}) {
  return {
    rooms: [],
    createdRoom: createRoom({ id: 99, name: 'General conversation' }),
    calls: {
      fetchRooms: 0,
      createPersonas: [],
      createRooms: [],
    },
    ...overrides,
  }
}

test('ensureDefaultConversation opens the most recent regular room', async () => {
  const latestRoom = createRoom({
    id: 12,
    name: 'Recent room',
    created_at: '2026-02-01T00:00:00.000Z',
    last_message_at: '2026-02-03T00:00:00.000Z',
  })
  const state = createMockState({
    rooms: [
      createRoom({ id: 1, created_at: '2026-02-02T00:00:00.000Z', type: 'battle_prep' }),
      createRoom({ id: 2, name: 'Older room', created_at: '2026-01-01T00:00:00.000Z' }),
      latestRoom,
    ],
  })
  const { ensureDefaultConversation } = await loadDefaultConversationModule(state)

  const room = await ensureDefaultConversation()

  assert.equal(room, latestRoom)
  assert.equal(state.calls.fetchRooms, 1)
  assert.equal(state.calls.createPersonas.length, 0)
  assert.equal(state.calls.createRooms.length, 0)
})

test('ensureDefaultConversation creates a temporary default persona and private room when needed', async () => {
  const state = createMockState()
  const { ensureDefaultConversation } = await loadDefaultConversationModule(state)

  const room = await ensureDefaultConversation()

  assert.equal(room.id, 99)
  assert.equal(state.calls.createPersonas.length, 1)
  assert.match(state.calls.createPersonas[0].id, /^default-conversation-partner-/)
  assert.equal(state.calls.createPersonas[0].temporary, true)
  assert.equal(state.calls.createRooms.length, 1)
  assert.equal(state.calls.createRooms[0].name, 'General conversation')
  assert.equal(state.calls.createRooms[0].type, 'private')
  assert.deepEqual(state.calls.createRooms[0].persona_ids, [state.calls.createPersonas[0].id])
})

test('ensureDefaultConversation coalesces concurrent default room creation', async () => {
  const state = createMockState()
  const { ensureDefaultConversation } = await loadDefaultConversationModule(state)

  const [first, second] = await Promise.all([
    ensureDefaultConversation(),
    ensureDefaultConversation(),
  ])

  assert.equal(first, second)
  assert.equal(state.calls.fetchRooms, 1)
  assert.equal(state.calls.createPersonas.length, 1)
  assert.equal(state.calls.createRooms.length, 1)
})
