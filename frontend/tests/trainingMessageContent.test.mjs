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

const trainingMessageContent = await loadTsModule('src/utils/trainingMessageContent.ts', 'training-message-content')

test('stripTrainingCoachNotesFromCounterpart removes drill coaching notes from the display copy', () => {
  const text = '我听起来像是便宜，但满100-90具体能用在哪些项目？\n\n小提醒：你这句太短了，信任感不够。'

  assert.equal(
    trainingMessageContent.stripTrainingCoachNotesFromCounterpart(text),
    '我听起来像是便宜，但满100-90具体能用在哪些项目？',
  )
})

test('stripTrainingCoachNotesFromCounterpart keeps ordinary customer text intact', () => {
  const text = '我想确认一下，这个优惠是否包含安装服务？'

  assert.equal(
    trainingMessageContent.stripTrainingCoachNotesFromCounterpart(text),
    text,
  )
})
