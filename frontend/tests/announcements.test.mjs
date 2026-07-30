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

function createStorage() {
  const entries = new Map()
  return {
    getItem(key) {
      return entries.has(key) ? entries.get(key) : null
    },
    setItem(key, value) {
      entries.set(key, String(value))
    },
  }
}

test('announcement client uses the TalkWise read-only endpoint and normalizes data', async () => {
  const calls = []
  const announcements = await loadTsModule('src/services/announcements.ts', 'announcements-client')
  const feed = await announcements.fetchAnnouncementFeed(async (url, init) => {
    calls.push({ url, init })
    return {
      ok: true,
      json: async () => ({
        data: {
          state: 'available',
          notice: ' 训练服务更新 ',
          announcements: [
            {
              id: 7,
              content: ' 新训练模板已发布 ',
              extra: ' 适用于销售沟通 ',
              published_at: '2026-07-29T09:00:00Z',
              type: 'success',
            },
          ],
        },
      }),
    }
  })

  assert.deepEqual(calls, [{
    url: '/api/v1/announcements',
    init: { method: 'GET', credentials: 'same-origin' },
  }])
  assert.deepEqual(feed, {
    state: 'available',
    notice: '训练服务更新',
    announcements: [{
      id: '7',
      content: '新训练模板已发布',
      extra: '适用于销售沟通',
      publishedAt: '2026-07-29T09:00:00Z',
      type: 'success',
    }],
  })
})

test('announcement client returns a neutral unavailable state without upstream error text', async () => {
  const announcements = await loadTsModule('src/services/announcements.ts', 'announcements-unavailable')
  const feed = await announcements.fetchAnnouncementFeed(async () => ({
    ok: false,
    json: async () => ({ detail: 'private upstream configuration' }),
  }))

  assert.deepEqual(feed, announcements.UNAVAILABLE_ANNOUNCEMENT_FEED)
  assert.doesNotMatch(JSON.stringify(feed), /private/i)
})

test('announcement read state persists locally and recognizes stable ids', async () => {
  const localStorage = createStorage()
  globalThis.window = { localStorage }
  const announcements = await loadTsModule('src/services/announcements.ts', 'announcements-read-state')
  const feed = {
    state: 'available',
    notice: '维护提醒',
    announcements: [{
      id: 'a-1',
      content: '训练日程调整',
      extra: null,
      publishedAt: null,
      type: 'warning',
    }],
  }
  const initial = announcements.loadAnnouncementReadState()
  const next = announcements.markAnnouncementFeedRead(initial, feed)
  announcements.persistAnnouncementReadState(next)

  assert.equal(announcements.unreadAnnouncementCount(initial, feed), 2)
  assert.equal(announcements.unreadAnnouncementCount(next, feed), 0)
  assert.equal(announcements.isAnnouncementRead(next, feed.announcements[0]), true)
  assert.equal(announcements.loadAnnouncementReadState().announcementKeys[0], 'id:a-1')
  delete globalThis.window
})

test('TopBar uses the announcement hook and the shared workbench route', () => {
  const source = fs.readFileSync(path.resolve('src/components/layout/TopBar.tsx'), 'utf8')

  assert.match(source, /useAnnouncements/)
  assert.match(source, /APP_ROUTES\.workbench/)
  assert.doesNotMatch(source, /to="\/"/)
})
