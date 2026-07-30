import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadRoomListModule() {
  const sourcePath = path.resolve('src/services/roomList.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `room-list-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

function createRoom(overrides = {}) {
  return {
    id: 1,
    name: 'General conversation',
    type: 'private',
    persona_ids: ['coach'],
    created_at: '2026-07-20T09:00:00',
    last_message_at: null,
    ...overrides,
  }
}

const roomList = await loadRoomListModule()

test('filterRooms searches room names and personas while preserving recent-first order', () => {
  const rooms = [
    createRoom({
      id: 1,
      name: 'Older private room',
      persona_ids: ['buyer'],
      created_at: '2026-07-18T09:00:00',
      last_message_at: '2026-07-19T09:00:00',
    }),
    createRoom({
      id: 2,
      name: 'Enterprise renewal',
      type: 'battle_prep',
      persona_ids: ['Alice'],
      created_at: '2026-07-21T09:00:00',
      last_message_at: '2026-07-27T10:00:00',
    }),
    createRoom({
      id: 3,
      name: 'Team alignment',
      type: 'group',
      persona_ids: ['pm', 'designer'],
      created_at: '2026-07-22T09:00:00',
      last_message_at: '2026-07-26T10:00:00',
    }),
  ]

  assert.deepEqual(roomList.filterRooms(rooms).map((room) => room.id), [2, 3, 1])
  assert.deepEqual(roomList.filterRooms(rooms, { filter: 'training' }).map((room) => room.id), [2])
  assert.deepEqual(roomList.filterRooms(rooms, { filter: 'conversation' }).map((room) => room.id), [3, 1])
  assert.deepEqual(roomList.filterRooms(rooms, { query: 'alice' }).map((room) => room.id), [2])
})

test('getRoomDisplayName hides generated training prefixes without changing ordinary titles', () => {
  assert.equal(roomList.getRoomDisplayName('Training: Regional sales review'), 'Regional sales review')
  assert.equal(roomList.getRoomDisplayName('training：董事会答辩'), '董事会答辩')
  assert.equal(roomList.getRoomDisplayName('备战: Alex'), 'Alex')
  assert.equal(roomList.getRoomDisplayName('备战：直属负责人'), '直属负责人')
  assert.equal(roomList.getRoomDisplayName('Customer renewal'), 'Customer renewal')
})

test('groupRoomsByActivity buckets active rooms into time sections', () => {
  const now = new Date(2026, 6, 27, 12, 0, 0)
  const groups = roomList.groupRoomsByActivity([
    createRoom({ id: 1, name: 'Today', last_message_at: '2026-07-27T09:00:00' }),
    createRoom({ id: 2, name: 'This week', last_message_at: '2026-07-24T09:00:00' }),
    createRoom({
      id: 3,
      name: 'Earlier',
      created_at: '2026-06-01T09:00:00',
      last_message_at: '2026-06-20T09:00:00',
    }),
    createRoom({ id: 4, name: 'Empty', created_at: null, last_message_at: null }),
  ], now)

  assert.deepEqual(groups.map((group) => group.id), [
    'today',
    'previous_7_days',
    'earlier',
    'no_activity',
  ])
  assert.deepEqual(groups.map((group) => group.rooms.map((room) => room.id)), [[1], [2], [3], [4]])
})

test('ChatPage exposes the room list as a mobile drawer instead of horizontal list scrolling', () => {
  const source = readSource('src/pages/ChatPage.tsx')
  const css = readSource('src/pages/ChatPage.css')

  assert.match(source, /roomListMobileOpen/)
  assert.match(source, /handleRoomListTouchStart/)
  assert.match(source, /onTouchEnd=\{handleRoomListTouchEnd\}/)
  assert.match(source, /chat-page-left-edge-tab/)
  assert.match(css, /\.chat-page\.has-room \.chat-page-left[\s\S]*translateX\(-102%\)/)
  assert.match(css, /\.chat-page\.has-room\.mobile-list-open \.chat-page-left[\s\S]*translateX\(0\)/)
})

test('RoomList keeps search local and shows room rows as title-only items', () => {
  const source = readSource('src/components/RoomList.tsx')
  const css = readSource('src/components/RoomList.css')

  assert.match(source, /Filter current conversations/)
  assert.match(source, /collapsedGroups/)
  assert.match(source, /getRoomDisplayName\(room\.name\)/)
  assert.match(source, /aria-expanded=\{!collapsed\}/)
  assert.match(source, /<ChevronDown size=\{13\} aria-hidden="true" \/>/)
  assert.doesNotMatch(source, /<small>\{group\.rooms\.length\}<\/small>/)
  assert.doesNotMatch(source, /room-list-prep-create/)
  assert.doesNotMatch(source, /roomMetaText/)
  assert.doesNotMatch(source, /roomTypeLabel/)
  assert.doesNotMatch(source, /room-personas/)
  assert.doesNotMatch(css, /room-list-prep-create/)
  assert.doesNotMatch(css, /room-list-group-heading small/)
  assert.doesNotMatch(css, /room-personas/)
  assert.match(css, /\.room-list-group-heading\.collapsed svg/)
})
