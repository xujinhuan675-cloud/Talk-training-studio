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
