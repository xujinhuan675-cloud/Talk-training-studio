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
  const appRoutesImportPattern = /from\s+['"]\.\/appRoutes['"]/
  if (appRoutesImportPattern.test(outputText)) {
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
    outputText = outputText.replace(appRoutesImportPattern, `from '${pathToFileURL(appRoutesPath).href}'`)
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

test('getRouteTitleKey resolves static and dynamic route titles', async () => {
  const routeTitles = await loadTsModule('src/routeTitles.ts', 'route-titles')

  assert.equal(routeTitles.getRouteTitleKey('/'), 'nav.home')
  assert.equal(routeTitles.getRouteTitleKey('/practice/scenarios'), 'nav.scenarioTraining')
  assert.equal(routeTitles.getRouteTitleKey('/practice/custom'), 'nav.trainingStudio')
  assert.equal(routeTitles.getRouteTitleKey('/practice/live-coach'), 'nav.liveCoach')
  assert.equal(routeTitles.getRouteTitleKey('/conversations/42'), 'nav.conversations')
  assert.equal(routeTitles.getRouteTitleKey('/chat/42'), 'nav.conversations')
  assert.equal(routeTitles.getRouteTitleKey('/review/sessions/session-1'), 'nav.review')
  assert.equal(routeTitles.getRouteTitleKey('/growth/leaderboard'), 'nav.scenarioLeaderboard')
  assert.equal(routeTitles.getRouteTitleKey('/config/scenarios'), 'settings.tabs.training')
  assert.equal(routeTitles.getRouteTitleKey('/config/personas/persona-1/edit'), 'settings.tabs.personas')
})

test('getRouteTitleKey follows settings query tabs when pathname is stable', async () => {
  const routeTitles = await loadTsModule('src/routeTitles.ts', 'route-titles-settings')

  assert.equal(routeTitles.getRouteTitleKey('/config'), 'nav.settings')
  assert.equal(routeTitles.getRouteTitleKey('/config', '?tab=personas'), 'settings.tabs.personas')
  assert.equal(routeTitles.getRouteTitleKey('/config', '?tab=scenarios'), 'settings.tabs.scenarios')
  assert.equal(routeTitles.getRouteTitleKey('/config', '?tab=organizations'), 'settings.tabs.organizations')
  assert.equal(routeTitles.getRouteTitleKey('/config', '?tab=config'), 'settings.tabs.config')
  assert.equal(routeTitles.getRouteTitleKey('/config', '?tab=unknown'), 'nav.settings')
})

test('getDocumentTitle formats translated page titles with the app name', async () => {
  const routeTitles = await loadTsModule('src/routeTitles.ts', 'route-titles-document')
  const translate = (key) => `translated:${key}`

  assert.equal(
    routeTitles.getDocumentTitle('/practice/battle-prep', '', translate),
    'translated:nav.battlePrep | TalkWise',
  )
  assert.equal(routeTitles.formatDocumentTitle(''), 'TalkWise')
})
