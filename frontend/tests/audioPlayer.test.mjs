import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadAudioPlayerModule() {
  const sourcePath = path.resolve('src/services/audioPlayer.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(os.tmpdir(), `audio-player-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const { AudioPlayQueue } = await loadAudioPlayerModule()

test('AudioPlayQueue reports playback runtime failures instead of swallowing them', async () => {
  const previousWindow = globalThis.window
  globalThis.window = {}
  const errors = []
  const queue = new AudioPlayQueue({
    onError: (_error, detail) => errors.push(detail.reason),
  })

  try {
    queue.setMuted(false)
    assert.equal(queue.enqueue('persona-1', Buffer.from('not-a-real-mp3').toString('base64')), true)

    await new Promise((resolve) => setTimeout(resolve, 20))
  } finally {
    queue.destroy()
    if (previousWindow === undefined) {
      delete globalThis.window
    } else {
      globalThis.window = previousWindow
    }
  }

  assert.deepEqual(errors, ['audio_context_unavailable'])
})
