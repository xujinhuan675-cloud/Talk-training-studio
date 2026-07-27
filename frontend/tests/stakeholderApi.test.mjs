import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadApiModule() {
  const sourcePath = path.resolve('src/services/api.ts')
  let outputText = ts.transpileModule(fs.readFileSync(sourcePath, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const cleanupPaths = []

  if (outputText.includes("from './auth'")) {
    const authOutput = ts.transpileModule(
      fs.readFileSync(path.resolve('src/services/auth.ts'), 'utf8'),
      {
        compilerOptions: {
          module: ts.ModuleKind.ES2022,
          target: ts.ScriptTarget.ES2022,
        },
      },
    ).outputText
    const authPath = path.join(os.tmpdir(), `stakeholder-api-auth-${process.pid}-${Date.now()}.mjs`)
    fs.writeFileSync(authPath, authOutput)
    cleanupPaths.push(authPath)
    outputText = outputText.replace(
      "from './auth'",
      `from '${pathToFileURL(authPath).href}'`,
    )
  }

  if (outputText.includes("from '../utils/errors'")) {
    const errorsOutput = ts.transpileModule(
      fs.readFileSync(path.resolve('src/utils/errors.ts'), 'utf8'),
      {
        compilerOptions: {
          module: ts.ModuleKind.ES2022,
          target: ts.ScriptTarget.ES2022,
        },
      },
    ).outputText
    const errorsPath = path.join(os.tmpdir(), `stakeholder-api-errors-${process.pid}-${Date.now()}.mjs`)
    fs.writeFileSync(errorsPath, errorsOutput)
    cleanupPaths.push(errorsPath)
    outputText = outputText.replace(
      "from '../utils/errors'",
      `from '${pathToFileURL(errorsPath).href}'`,
    )
  }

  const outputPath = path.join(os.tmpdir(), `stakeholder-api-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, outputText)
  cleanupPaths.push(outputPath)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    cleanupPaths.forEach((item) => fs.rmSync(item, { force: true }))
  }
}

const api = await loadApiModule()

function createStorage(initial = {}) {
  const store = new Map(Object.entries(initial))
  return {
    get length() {
      return store.size
    },
    getItem(key) {
      return store.has(key) ? store.get(key) : null
    },
    setItem(key, value) {
      store.set(key, String(value))
    },
    removeItem(key) {
      store.delete(key)
    },
    clear() {
      store.clear()
    },
    key(index) {
      return Array.from(store.keys())[index] ?? null
    },
  }
}

function installMockSalesAuthWindow() {
  globalThis.window = {
    localStorage: createStorage({
      'talkwise.auth.state': JSON.stringify({ status: 'authenticated', userId: 'sales' }),
    }),
    sessionStorage: createStorage(),
  }
}

test('fetchRoomDetail sends training session guard and mock auth headers', async () => {
  installMockSalesAuthWindow()
  let request = null
  globalThis.fetch = async (url, init) => {
    request = { url, init }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        code: 0,
        message: 'ok',
        data: {
          room: {
            id: 42,
            name: 'Training',
            type: 'battle_prep',
            persona_ids: ['training-runtime'],
            created_at: null,
            last_message_at: null,
          },
          messages: [],
        },
      }),
    }
  }

  const detail = await api.fetchRoomDetail(42, { trainingSessionId: 'session-1' })

  assert.equal(detail.room.id, 42)
  assert.equal(request.url, '/api/v1/stakeholder/rooms/42?trainingSessionId=session-1')
  assert.equal(request.init.credentials, 'same-origin')
  assert.equal(request.init.headers.get('X-Mock-User'), 'sales')
  assert.equal(request.init.headers.get('X-User-Id'), 'user-sales-001')
  assert.equal(request.init.headers.get('X-Team-Id'), 'team-revenue')
})

test('room stream url carries training session and mock auth query params', () => {
  installMockSalesAuthWindow()

  const url = new URL(api.getRoomStreamUrl(42, { trainingSessionId: 'session-1' }), 'http://test')

  assert.equal(url.pathname, '/api/v1/stakeholder/rooms/42/stream')
  assert.equal(url.searchParams.get('trainingSessionId'), 'session-1')
  assert.equal(url.searchParams.get('mock_user'), 'sales')
  assert.equal(url.searchParams.get('auth_user_id'), 'user-sales-001')
  assert.equal(url.searchParams.get('auth_team_id'), 'team-revenue')
})

test('startBattle surfaces backend validation message', async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 422,
    json: async () => ({
      code: 1004,
      message: 'Validation failed: List should have at most 5 items',
      error: {
        type: 'ValidationError',
        details: {
          errors: [
            {
              loc: ['body', 'selected_training_points'],
              msg: 'List should have at most 5 items',
            },
          ],
        },
      },
    }),
  })

  await assert.rejects(
    () => api.startBattle({
      persona_name: 'Interviewer',
      persona_role: 'AI product interviewer',
      persona_style: 'Evidence-oriented.',
      scenario_context: 'A comprehensive interview.',
      selected_training_points: ['a', 'b', 'c', 'd', 'e', 'f'],
      difficulty: 'hard',
    }),
    /List should have at most 5 items/,
  )
})

test('startBattle sends selected AI reply language', async () => {
  let requestBody = null
  globalThis.fetch = async (_url, init) => {
    requestBody = JSON.parse(init.body)
    return {
      ok: true,
      status: 201,
      json: async () => ({
        code: 0,
        message: 'ok',
        data: {
          id: 7,
          name: '备战: Alex',
          type: 'battle_prep',
          persona_ids: ['bp-alex'],
          created_at: null,
          last_message_at: null,
        },
      }),
    }
  }

  const room = await api.startBattle({
    persona_name: 'Alex',
    persona_role: 'VP Sales',
    persona_style: 'Direct and skeptical.',
    scenario_context: 'Budget review.',
    selected_training_points: ['Handle budget objections'],
    difficulty: 'normal',
    reply_language: 'en-US',
  })

  assert.equal(room.id, 7)
  assert.equal(requestBody.reply_language, 'en-US')
})
