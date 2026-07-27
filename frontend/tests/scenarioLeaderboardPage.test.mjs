import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

test('ScenarioLeaderboardPage uses the current NewAPI team members for Team Board', () => {
  const source = readSource('src/pages/ScenarioLeaderboardPage.tsx')

  assert.match(source, /fetchCurrentTeamMembers/)
  assert.match(source, /const isNewApiSession = currentUser\?\.authProvider === 'newapi'/)
  assert.match(source, /setNewApiTeam\(payload\.team\)/)
  assert.match(source, /payload\.members\.map\(\(member\) => \(/)
  assert.match(source, /newApiMemberToLeaderboardUser\(member, currentUser, payload\.team\)/)
  assert.match(source, /userId: `newapi:\$\{member\.userId\}`/)
  assert.match(source, /return visibleUsersForViewer\(users, currentUser\)\.map\(authUserToLeaderboardUser\)/)
})

test('ScenarioLeaderboardPage shows total current team members as the headline count', () => {
  const source = readSource('src/pages/ScenarioLeaderboardPage.tsx')

  assert.match(source, /<small>\{tr\('当前成员', 'Members'\)\}<\/small>/)
  assert.match(source, /<strong>\{summary\.totalUsers\}<\/strong>/)
  assert.match(source, /count: team\.participants/)
})

test('ScenarioLeaderboardPage labels NewAPI Team Board by the loaded current team', () => {
  const source = readSource('src/pages/ScenarioLeaderboardPage.tsx')

  assert.match(source, /const teamLabel = isNewApiSession/)
  assert.match(source, /newApiTeam\?\.name \?\? currentUser\?\.teamName/)
  assert.match(source, /: currentUser\?\.systemRole === 'admin'/)
  assert.match(source, /'All teams'/)
})

test('ScenarioLeaderboardPage splits dense management content into secondary tabs', () => {
  const source = readSource('src/pages/ScenarioLeaderboardPage.tsx')
  const css = readSource('src/pages/ScenarioLeaderboardPage.css')

  assert.match(source, /type LeaderboardViewTab = 'overview' \| 'unfinished' \| 'insights' \| 'personal'/)
  assert.match(source, /activeBoardTab, setActiveBoardTab/)
  assert.match(source, /scenario-leaderboard-view-tabs/)
  assert.match(source, /Team board view/)
  assert.match(source, /activeBoardTab === 'overview'/)
  assert.match(source, /activeBoardTab === 'insights'/)
  assert.match(source, /activeBoardTab === 'unfinished'/)
  assert.match(source, /activeBoardTab === 'personal'/)
  assert.match(source, /\(!isManagementView \|\| activeBoardTab === 'personal'\)/)
  assert.match(css, /\.scenario-leaderboard-view-nav/)
  assert.match(css, /\.scenario-leaderboard-grid--overview/)
  assert.match(css, /\.scenario-leaderboard-side--tab/)
})

test('ScenarioLeaderboardPage keeps member switching inside the member performance tab', () => {
  const source = readSource('src/pages/ScenarioLeaderboardPage.tsx')
  const css = readSource('src/pages/ScenarioLeaderboardPage.css')
  const headerStart = source.indexOf('<PageHeader')
  const headerEnd = source.indexOf('{teamMembersLoading', headerStart)
  const header = source.slice(headerStart, headerEnd)
  const personalStart = source.indexOf('<section className="scenario-leaderboard-personal"')
  const personal = source.slice(personalStart)
  const memberSelectStart = personal.indexOf('scenario-leaderboard-member-select')
  const memberSelectEnd = personal.indexOf('</Select>', memberSelectStart)
  const memberSelect = personal.slice(memberSelectStart, memberSelectEnd)

  assert.notEqual(headerStart, -1)
  assert.notEqual(headerEnd, -1)
  assert.notEqual(personalStart, -1)
  assert.notEqual(memberSelectStart, -1)
  assert.notEqual(memberSelectEnd, -1)
  assert.match(header, /scenario-leaderboard-link/)
  assert.doesNotMatch(header, /scenario-leaderboard-member-select|setSelectedUserId/)
  assert.match(personal, /scenario-leaderboard-member-select/)
  assert.match(personal, /onChange=\{\(event\) => setSelectedUserId\(event\.target\.value\)\}/)
  assert.match(memberSelect, /\{user\.name\}/)
  assert.doesNotMatch(memberSelect, /user\.teamName/)
  assert.match(css, /\.scenario-leaderboard-member-select/)
  assert.match(css, /\.scenario-leaderboard-select > span[\s\S]*white-space:\s*nowrap/)
})
