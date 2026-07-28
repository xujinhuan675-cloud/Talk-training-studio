import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

test('Settings members tab keeps the add-member search above the member list', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const tabStart = source.indexOf('function TeamMembersTab()')
  const searchPanel = source.indexOf('settings-member-search-panel', tabStart)
  const memberList = source.indexOf('className="settings-list"', searchPanel)

  assert.notEqual(tabStart, -1)
  assert.notEqual(searchPanel, -1)
  assert.notEqual(memberList, -1)
  assert.ok(searchPanel < memberList)
})

test('Settings tabs keep tab labels from repeating as section titles', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const tabRanges = [
    ['personas', 'function PersonasTab()', '// Scenarios Tab'],
    ['scenarios', 'function ScenariosTab()', '// Team Members Tab'],
    ['members', 'function TeamMembersTab()', '// Organizations Tab'],
    ['organizations', 'function OrganizationsTab()', '// Preferences Tab'],
    ['config', 'function ConfigTab()', '// SettingsPage'],
  ]

  for (const [name, startMarker, endMarker] of tabRanges) {
    const tabStart = source.indexOf(startMarker)
    const tabEnd = source.indexOf(endMarker, tabStart)
    const tab = source.slice(tabStart, tabEnd)

    assert.notEqual(tabStart, -1, `${name} tab start not found`)
    assert.notEqual(tabEnd, -1, `${name} tab end not found`)
    assert.match(tab, /settings-section-header actions-only/, `${name} tab should align actions to the right`)
    assert.match(tab, /settings-header-actions/, `${name} tab should use the shared action wrapper`)
    assert.doesNotMatch(tab, /settings-section-title/, `${name} tab should not repeat its tab label`)
  }
})

test('Settings organization subtabs use content-sized secondary tab layout', () => {
  const css = readSource('src/pages/SettingsPage.css')
  const orgTabsBlock = css.match(/\.settings-org-tabs\.ui-segmented-control\s*\{([\s\S]*?)\n\}/)?.[1]
  const orgTabButtonBlock = css.match(/\.settings-org-tabs \.ui-segmented-control-button\s*\{([\s\S]*?)\n\}/)?.[1]

  assert.ok(orgTabsBlock)
  assert.ok(orgTabButtonBlock)
  assert.match(orgTabsBlock, /align-self:\s*flex-start/)
  assert.match(orgTabsBlock, /max-width:\s*100%/)
  assert.match(orgTabsBlock, /overflow-x:\s*auto/)
  assert.doesNotMatch(orgTabsBlock, /(^|\n)\s*width:\s*100%/)
  assert.match(orgTabButtonBlock, /flex:\s*0 0 auto/)
  assert.doesNotMatch(orgTabButtonBlock, /flex:\s*1/)
})

test('Settings personas tab deduplicates repeated display identities', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const tabStart = source.indexOf('function PersonasTab()')
  const tabEnd = source.indexOf('// Scenarios Tab', tabStart)
  const personasTab = source.slice(tabStart, tabEnd)

  assert.match(source, /function personaDisplayKey/)
  assert.match(source, /function dedupePersonasForDisplay/)
  assert.match(source, /new Map<string, PersonaSummary>/)
  assert.match(source, /!current\.supports_v2 && persona\.supports_v2/)
  assert.match(personasTab, /dedupePersonasForDisplay\(Object\.values\(personaMap\)\)/)
  assert.match(personasTab, /countAudienceFilters\(displayPersonas, personaAudienceValues\)/)
  assert.match(personasTab, /matchesAudienceFilter\(values, personaAudience\)/)
  assert.match(personasTab, /matchesSearchQuery\(values, personaQuery\)/)
  assert.match(personasTab, /visiblePersonas\.map/)
  assert.doesNotMatch(personasTab, /personas\.map\(\(p\)/)
})

test('Settings personas and scenarios use member-style local search panels with audience dropdowns before their lists', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const css = readSource('src/pages/SettingsPage.css')
  const personasStart = source.indexOf('function PersonasTab()')
  const personasEnd = source.indexOf('// Scenarios Tab', personasStart)
  const scenariosStart = source.indexOf('function ScenariosTab()')
  const scenariosEnd = source.indexOf('// Team Members Tab', scenariosStart)
  const personasTab = source.slice(personasStart, personasEnd)
  const scenariosTab = source.slice(scenariosStart, scenariosEnd)

  assert.notEqual(personasStart, -1)
  assert.notEqual(personasEnd, -1)
  assert.notEqual(scenariosStart, -1)
  assert.notEqual(scenariosEnd, -1)
  assert.match(source, /function matchesSearchQuery/)
  assert.match(source, /type AudienceFilter = 'all' \| 'sales' \| 'customer_service' \| 'management' \| 'hr_interview' \| 'negotiation' \| 'general'/)
  assert.match(source, /BUSINESS_AUDIENCE_KEYWORDS/)
  assert.match(source, /function inferBusinessAudienceValues/)
  assert.match(source, /future explicit audience\/use\/department fields can replace it/)
  assert.match(source, /function audienceFilterLabel/)
  assert.match(source, /Sales \{count\}/)
  assert.match(source, /Customer service \{count\}/)
  assert.match(source, /HR \/ Interview \{count\}/)
  assert.match(personasTab, /personaQuery/)
  assert.match(personasTab, /personaAudience/)
  assert.match(personasTab, /settings-form-panel settings-list-filter-panel/)
  assert.match(personasTab, /settings-member-search-form settings-list-filter-form/)
  assert.match(personasTab, /settings-list-filter-select/)
  assert.match(personasTab, /Persona audience/)
  assert.doesNotMatch(personasTab, /settings-list-filter-group|<SegmentedControl/)
  assert.doesNotMatch(personasTab, /Basic personas|New personas|Persona type/)
  assert.match(personasTab, /Filter persona name or role/)
  assert.ok(personasTab.indexOf('settings-list-filter-panel') < personasTab.indexOf('<div className="settings-list">'))
  assert.match(scenariosTab, /scenarioQuery/)
  assert.match(scenariosTab, /scenarioAudience/)
  assert.match(scenariosTab, /visibleScenarios = useMemo/)
  assert.match(scenariosTab, /scenarioAudienceValues\(scenario, scenarioPersonaLookup\)/)
  assert.match(scenariosTab, /settings-list-filter-select/)
  assert.match(scenariosTab, /Room scenario audience/)
  assert.doesNotMatch(scenariosTab, /settings-list-filter-group|<SegmentedControl/)
  assert.doesNotMatch(scenariosTab, /Linked personas|Unlinked personas|Room scenario type/)
  assert.match(scenariosTab, /Filter scenario name, description, or persona/)
  assert.ok(scenariosTab.indexOf('settings-list-filter-panel') < scenariosTab.indexOf('<div className="settings-list">'))
  assert.match(css, /\.settings-list-filter-form\.settings-member-search-form/)
  assert.match(css, /grid-template-columns:\s*minmax\(220px, 1fr\) auto auto/)
  assert.match(css, /\.settings-list-filter-select \.ui-form-select/)
  assert.doesNotMatch(css, /settings-list-filter-group/)
})

test('Settings scenarios edit in a dialog instead of an inline form panel', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const css = readSource('src/pages/SettingsPage.css')
  const scenariosStart = source.indexOf('function ScenariosTab()')
  const scenariosEnd = source.indexOf('// Team Members Tab', scenariosStart)
  const scenariosTab = source.slice(scenariosStart, scenariosEnd)

  assert.notEqual(scenariosStart, -1)
  assert.notEqual(scenariosEnd, -1)
  assert.match(scenariosTab, /<Dialog open=\{showForm\}/)
  assert.match(scenariosTab, /DialogContent className="settings-scenario-dialog"/)
  assert.match(scenariosTab, /settings-scenario-dialog-close/)
  assert.doesNotMatch(scenariosTab, /\{showForm && \(\s*<div className="settings-form-panel">/)
  assert.match(css, /\.settings-scenario-dialog\.ui-dialog-content/)
  assert.match(css, /\.settings-voice-dialog\.ui-dialog-content[\s\S]*transform:\s*translate\(-50%, -50%\)/)
})

test('Settings AI service cards omit provider catalog rows but keep dialog catalog summaries', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const css = readSource('src/pages/SettingsPage.css')
  const meta = source.match(/<span className="settings-voice-module-meta">([\s\S]*?)<\/span>\s*<ChevronRight/)

  assert.doesNotMatch(source, /settings-voice-module-catalog/)
  assert.doesNotMatch(css, /settings-voice-module-catalog/)
  assert.doesNotMatch(source, /Pipecat LLM: \{count\} providers/)
  assert.doesNotMatch(source, /countCatalogProviders/)
  assert.doesNotMatch(source, /module\.provider|module\.note|voiceProviderLabel|configStatusText|sourceText/)
  assert.doesNotMatch(css, /settings-voice-module-meta span|settings-voice-module-meta small/)
  assert.ok(meta)
  assert.match(meta[1], /<strong>\{module\.model\}<\/strong>/)
  assert.doesNotMatch(meta[1], /<small>|module\.provider|module\.note/)
  assert.match(source, /renderCatalogSummary\(llmChannel, 'Pipecat LLM'\)/)
})

test('Settings TTS card uses backend runtime availability, not only configured keys', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const configStart = source.indexOf('function ConfigTab()')
  const config = source.slice(configStart)

  assert.notEqual(configStart, -1)
  assert.match(config, /config\?\.tts_runtime_available \?\? Boolean\(config\?\.tts_api_key_configured\)/)
  assert.match(config, /renderTtsRuntimeNote/)
  assert.match(config, /tts_runtime_message/)
})

test('Settings AI service shows readable errors and neutral inventory realtime state', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const css = readSource('src/pages/SettingsPage.css')
  const voiceConfig = readSource('src/services/voiceConfig.ts')
  const configStart = source.indexOf('function ConfigTab()')
  const config = source.slice(configStart)

  assert.notEqual(configStart, -1)
  assert.match(source, /getErrorMessage as getReadableErrorMessage/)
  assert.match(source, /return getReadableErrorMessage\(error\)/)
  assert.doesNotMatch(source, /return error instanceof Error \? error\.message : String\(error\)/)
  assert.match(voiceConfig, /function errorMessageFromPayload/)
  assert.match(voiceConfig, /const message = errorMessageFromPayload\(json\)/)
  assert.doesNotMatch(voiceConfig, /json\?\.error\?\.details \|\| detail/)
  assert.match(config, /if \(preset\?\.status === 'inventory'\) return 'neutral'/)
  assert.match(config, /const realtimeModuleTone = \(\): VoiceModuleTone =>/)
  assert.match(config, /tone: realtimeModuleTone\(\)/)
  assert.match(source, /module\.tone === 'neutral'[\s\S]*<Clock3 size=\{13\} \/>/)
  assert.match(css, /\.settings-voice-badge\.neutral\s*\{[\s\S]*border-color:\s*var\(--border\)/)
})

test('Settings AI service reset and dialog close controls stay out of primary action rows', () => {
  const source = readSource('src/pages/SettingsPage.tsx')
  const css = readSource('src/pages/SettingsPage.css')
  const configStart = source.indexOf('function ConfigTab()')
  const config = source.slice(configStart)
  const headerStart = config.indexOf('<div className="settings-section-header actions-only">')
  const listStart = config.indexOf('<div className="settings-voice-list"')
  const header = config.slice(headerStart, listStart)
  const bottomActions = config.match(/<div className="settings-form-actions settings-voice-actions">([\s\S]*?)<\/div>/)
  const dialog = config.match(/<DialogContent className="settings-voice-dialog">([\s\S]*?)<\/DialogContent>/)
  const dialogActions = dialog?.[1].match(/<div className="dialog-actions settings-voice-dialog-actions">([\s\S]*?)<\/div>/)

  assert.notEqual(configStart, -1)
  assert.doesNotMatch(header, /settings-section-title/)
  assert.match(header, /settings-reset-button/)
  assert.match(header, /<RotateCcw size=\{14\} \/>/)
  assert.match(header, /'Reset'/)
  assert.ok(bottomActions)
  assert.doesNotMatch(bottomActions[1], /loadConfig|Reset|RotateCcw|RefreshCw/)
  assert.ok(dialog)
  assert.match(dialog[1], /settings-voice-dialog-close/)
  assert.match(dialog[1], /<X size=\{16\} \/>/)
  assert.ok(dialogActions)
  assert.doesNotMatch(dialogActions[1], /variant="secondary"|Close/)
  assert.match(css, /\.settings-voice-dialog-close\.ui-button/)
})

test('Settings scroll containers use the shared global scrollbar style', () => {
  const indexCss = readSource('src/index.css')
  const settingsCss = readSource('src/pages/SettingsPage.css')
  const roomListCss = readSource('src/components/RoomList.css')

  assert.match(indexCss, /scrollbar-width:\s*thin/)
  assert.match(indexCss, /\*::-webkit-scrollbar/)
  assert.doesNotMatch(settingsCss, /::-webkit-scrollbar|scrollbar-width|scrollbar-color/)
  assert.doesNotMatch(roomListCss, /::-webkit-scrollbar|scrollbar-width|scrollbar-color/)
})
