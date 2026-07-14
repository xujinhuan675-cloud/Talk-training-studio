import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTrainingStudioModule() {
  const sourcePath = path.resolve('src/services/trainingStudio.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `training-studio-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const trainingStudio = await loadTrainingStudioModule()

test('default training studio config is product-manager interview oriented', () => {
  const config = trainingStudio.getDefaultTrainingStudioConfig()

  assert.equal(config.scenario, 'interview')
  assert.equal(config.interviewRolePreset, 'hiring_manager')
  assert.equal(config.interviewScenarioPreset, 'resume_deep_dive')
  assert.equal(config.role, 'Product Manager')
  assert.match(config.techStack, /interview/i)
})

test('interview scenario presets carry realistic interviewer counterparts', () => {
  const resumeDeepDive = trainingStudio.getInterviewScenarioPreset('resume_deep_dive')
  const productCase = trainingStudio.getInterviewScenarioPreset('product_sense_case')

  assert.equal(resumeDeepDive.fallbackPersonaName, 'Hiring Manager')
  assert.match(resumeDeepDive.fallbackPersonaRole, /resume claims/i)
  assert.equal(productCase.framework, 'scqa')
})

test('product scenario presets carry realistic stakeholder counterparts', () => {
  const prdReview = trainingStudio.getProductScenarioPreset('prd_review')
  const executiveUpdate = trainingStudio.getProductScenarioPreset('executive_update')

  assert.equal(prdReview.fallbackPersonaName, 'Engineering Lead')
  assert.match(prdReview.fallbackPersonaRole, /feasibility/i)
  assert.equal(executiveUpdate.difficulty, 'hard')
})

test('buildTrainingStudioPrompt includes interview round and interviewer context', () => {
  const config = trainingStudio.getDefaultTrainingStudioConfig()
  const prompt = trainingStudio.buildTrainingStudioPrompt(config, 'Practice a resume deep dive.')

  assert.match(prompt, /Interview/)
  assert.match(prompt, /Interview round: Resume deep dive/)
  assert.match(prompt, /Interviewer: Hiring manager/)
  assert.match(prompt, /Interview focus: resume project/)
})

test('buildTrainingStudioPrompt includes product drill and counterpart context', () => {
  const config = {
    ...trainingStudio.getDefaultTrainingStudioConfig(),
    scenario: 'product_management',
    productRolePreset: 'core_pm',
    productScenarioPreset: 'roadmap_prioritization',
  }
  const prompt = trainingStudio.buildTrainingStudioPrompt(config, 'Practice a roadmap trade-off.')

  assert.match(prompt, /Product Mgmt/)
  assert.match(prompt, /Product drill: Roadmap priority/)
  assert.match(prompt, /Counterpart: Head of Sales/)
  assert.match(prompt, /PM focus: roadmap prioritization/)
})

test('buildTrainingStudioPrompt omits product drill context outside product scenarios', () => {
  const config = {
    ...trainingStudio.getDefaultTrainingStudioConfig(),
    scenario: 'interview',
  }
  const prompt = trainingStudio.buildTrainingStudioPrompt(config, 'Practice an interview answer.')

  assert.doesNotMatch(prompt, /Product drill:/)
  assert.doesNotMatch(prompt, /Counterpart:/)
})
