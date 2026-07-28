import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function findRuleBlocks(css, selector) {
  const rulePattern = new RegExp(`(?:^|\\n)\\s*${escapeRegExp(selector)}\\s*\\{([\\s\\S]*?)\\n\\s*\\}`, 'g')
  return [...css.matchAll(rulePattern)].map((match) => match[1])
}

test('ScenarioConfigPage keeps secondary tabs content-sized instead of equal-width', () => {
  const source = readSource('src/pages/ScenarioConfigPage.tsx')
  const css = readSource('src/pages/ScenarioConfigPage.css')
  const tabOptionsStart = source.indexOf('const tabOptions = useMemo')
  const tabOptionsEnd = source.indexOf('const selectedWeightValidation', tabOptionsStart)
  const tabControlStart = source.indexOf('<SegmentedControl', source.indexOf('scenario-config-tabbar'))
  const tabControlEnd = source.indexOf('/>', tabControlStart)
  const tabOptionsSource = source.slice(tabOptionsStart, tabOptionsEnd)
  const tabControlSource = source.slice(tabControlStart, tabControlEnd)
  const tabbarBlock = findRuleBlocks(css, '.scenario-config-tabbar')[0]
  const tabBlocks = findRuleBlocks(css, '.scenario-config-tabs.ui-segmented-control')
  const tabButtonBlock = findRuleBlocks(css, '.scenario-config-tabs .ui-segmented-control-button')[0]
  const mainTabsBlock = tabBlocks[0]
  const mobileTabsBlock = tabBlocks[1]

  assert.notEqual(tabOptionsStart, -1)
  assert.notEqual(tabOptionsEnd, -1)
  assert.notEqual(tabControlStart, -1)
  assert.notEqual(tabControlEnd, -1)
  assert.ok(tabbarBlock)
  assert.ok(mainTabsBlock)
  assert.ok(mobileTabsBlock)
  assert.ok(tabButtonBlock)
  assert.match(tabControlSource, /size="sm"/)
  assert.match(tabbarBlock, /overflow-x:\s*auto/)
  assert.match(mainTabsBlock, /width:\s*fit-content/)
  assert.match(mainTabsBlock, /max-width:\s*100%/)
  assert.match(mainTabsBlock, /overflow-x:\s*auto/)
  assert.match(mainTabsBlock, /justify-content:\s*flex-start/)
  assert.doesNotMatch(mainTabsBlock, /display:\s*grid|grid-template-columns|(^|\n)\s*width:\s*100%/)
  assert.doesNotMatch(mainTabsBlock, /(^|\n)\s*(min-height|padding|gap|box-shadow|border|border-radius)\s*:/)
  assert.match(tabButtonBlock, /flex:\s*0 0 auto/)
  assert.doesNotMatch(tabButtonBlock, /flex:\s*1/)
  assert.doesNotMatch(tabButtonBlock, /(^|\n)\s*(min-height|padding|gap|box-shadow|border|border-radius)\s*:/)
  assert.match(mobileTabsBlock, /width:\s*fit-content/)
  assert.match(mobileTabsBlock, /max-width:\s*100%/)
  assert.doesNotMatch(mobileTabsBlock, /display:\s*grid|grid-template-columns|(^|\n)\s*width:\s*100%/)
  assert.doesNotMatch(tabOptionsSource, /scenario-config-tab-count|state\.scenarios\.length|state\.dimensions\.length/)
  assert.doesNotMatch(css, /scenario-config-tab-count/)
})

test('ScenarioConfigPage moves dense template and scoring fields into collapsible groups', () => {
  const source = readSource('src/pages/ScenarioConfigPage.tsx')
  const css = readSource('src/pages/ScenarioConfigPage.css')
  const contentStart = source.indexOf('<details className="scenario-config-section scenario-config-content-section">')
  const contentEnd = source.indexOf('<section className="scenario-config-weight-editor"', contentStart)
  const weightStart = source.indexOf('<details className="scenario-config-section scenario-config-weight-details">')
  const weightEnd = source.indexOf('{activeTab === \'dimensions\'', weightStart)
  const criteriaStart = source.indexOf('<details className="scenario-config-section scenario-config-dimension-criteria">')
  const criteriaEnd = source.indexOf('<div className="scenario-config-dimension-footer">', criteriaStart)
  const contentSection = source.slice(contentStart, contentEnd)
  const weightSection = source.slice(weightStart, weightEnd)
  const criteriaSection = source.slice(criteriaStart, criteriaEnd)
  const sectionBlock = findRuleBlocks(css, '.scenario-config-section')[0]
  const summaryBlock = findRuleBlocks(css, '.scenario-config-section-summary')[0]
  const bodyBlock = findRuleBlocks(css, '.scenario-config-section-body')[0]
  const weightEditorBlock = findRuleBlocks(css, '.scenario-config-weight-editor')[0]
  const weightDetailsBlock = findRuleBlocks(css, '.scenario-config-weight-details')[0]

  assert.notEqual(contentStart, -1)
  assert.notEqual(contentEnd, -1)
  assert.notEqual(weightStart, -1)
  assert.notEqual(weightEnd, -1)
  assert.notEqual(criteriaStart, -1)
  assert.notEqual(criteriaEnd, -1)
  assert.match(contentSection, /<summary className="scenario-config-section-summary">/)
  assert.match(contentSection, /Scenario description/)
  assert.match(contentSection, /Customer profile/)
  assert.match(contentSection, /Counterpart opening line/)
  assert.match(contentSection, /Persona name/)
  assert.match(contentSection, /Training points/)
  assert.match(weightSection, /<summary className="scenario-config-section-summary">/)
  assert.match(weightSection, /Weight details/)
  assert.match(weightSection, /scenario-config-weight-table/)
  assert.match(criteriaSection, /<summary className="scenario-config-section-summary">/)
  assert.match(criteriaSection, /Criteria definition/)
  assert.match(criteriaSection, /Scoring criteria/)
  assert.ok(sectionBlock)
  assert.ok(summaryBlock)
  assert.ok(bodyBlock)
  assert.ok(weightEditorBlock)
  assert.ok(weightDetailsBlock)
  assert.match(sectionBlock, /border-top:\s*1px solid var\(--config-border-soft\)/)
  assert.match(summaryBlock, /min-height:\s*42px/)
  assert.match(summaryBlock, /list-style:\s*none/)
  assert.match(bodyBlock, /display:\s*grid/)
  assert.match(weightEditorBlock, /border-top:\s*1px solid var\(--config-border-soft\)/)
  assert.doesNotMatch(weightEditorBlock, /border-radius|background:\s*var\(--config-surface-muted\)/)
  assert.match(weightDetailsBlock, /border-top:\s*0/)
})
