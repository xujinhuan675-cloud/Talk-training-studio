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
  let outputText = output.outputText
  const cleanupPaths = []
  if (outputText.includes("from './appRoutes'")) {
    const appRoutesSource = fs.readFileSync(path.resolve('src/appRoutes.ts'), 'utf8')
    const appRoutesOutput = ts.transpileModule(appRoutesSource, {
      compilerOptions: {
        module: ts.ModuleKind.ES2022,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText
    const appRoutesPath = path.join(os.tmpdir(), `app-routes-${process.pid}-${Date.now()}.mjs`)
    fs.writeFileSync(appRoutesPath, appRoutesOutput)
    cleanupPaths.push(appRoutesPath)
    outputText = outputText.replace("from './appRoutes'", `from '${pathToFileURL(appRoutesPath).href}'`)
  }
  const outputPath = path.join(os.tmpdir(), `${prefix}-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    cleanupPaths.forEach((item) => fs.rmSync(item, { force: true }))
    fs.rmSync(outputPath, { force: true })
  }
}

test('createRedirectTarget preserves query search and state reference', async () => {
  const redirects = await loadTsModule('src/routeRedirects.ts', 'route-redirects')
  const state = { from: '/legacy', nested: { step: 1 } }

  const result = redirects.createRedirectTarget('/conversations/42', {
    search: '?tab=notes&mode=review',
    state,
  })

  assert.equal(result.to, '/conversations/42?tab=notes&mode=review')
  assert.equal(result.state, state)
})

test('resolveConversationRoomRedirectTarget resolves room redirects', async () => {
  const redirects = await loadTsModule('src/routeRedirects.ts', 'route-redirects-conversation')

  assert.equal(redirects.resolveConversationRoomRedirectTarget(42), '/conversations/42')
  assert.equal(redirects.resolveConversationRoomRedirectTarget('room 7'), '/conversations/room%207')
})

test('resolveTrainingResultSessionRedirectTarget resolves training result redirects', async () => {
  const redirects = await loadTsModule('src/routeRedirects.ts', 'route-redirects-training-result')

  assert.equal(redirects.resolveTrainingResultSessionRedirectTarget(99), '/review/sessions/99')
  assert.equal(redirects.resolveTrainingResultSessionRedirectTarget('session 7'), '/review/sessions/session%207')
})

test('resolvePersonaEditRedirectTarget resolves persona edit redirects', async () => {
  const redirects = await loadTsModule('src/routeRedirects.ts', 'route-redirects-persona-edit')

  assert.equal(redirects.resolvePersonaEditRedirectTarget(17), '/config/personas/17/edit')
  assert.equal(redirects.resolvePersonaEditRedirectTarget('persona 7'), '/config/personas/persona%207/edit')
})
