import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadLiveCoachLanguagesModule() {
  const sourcePath = path.resolve('src/data/liveCoachLanguages.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `live-coach-languages-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const liveCoachLanguages = await loadLiveCoachLanguagesModule()

test('live coach language catalog keeps translation targets separate from UI locale', () => {
  assert.ok(liveCoachLanguages.LIVE_COACH_LANGUAGE_OPTIONS.length >= 70)
  assert.ok(liveCoachLanguages.LIVE_COACH_LANGUAGE_OPTIONS.some((option) => option.code === 'zh-CN'))
  assert.ok(liveCoachLanguages.LIVE_COACH_LANGUAGE_OPTIONS.some((option) => option.code === 'en-US'))
  assert.equal(liveCoachLanguages.getLiveCoachLanguageLabel('pt'), 'Portuguese')
  assert.equal(liveCoachLanguages.getLiveCoachLanguageLabel('zh-CN', 'zh'), '简体中文')
  assert.equal(liveCoachLanguages.getLiveCoachLanguageLabel('en-US', 'zh'), '英语（美国）')
  assert.equal(liveCoachLanguages.getLiveCoachLanguageLabel('es-419'), 'es-419')
})
