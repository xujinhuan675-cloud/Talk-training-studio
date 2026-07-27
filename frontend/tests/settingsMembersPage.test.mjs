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
