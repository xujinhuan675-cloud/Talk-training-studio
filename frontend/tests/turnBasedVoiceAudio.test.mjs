import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTurnBasedVoiceAudioModule() {
  const sourcePath = path.resolve('src/services/turnBasedVoiceAudio.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `turn-based-voice-audio-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

function asciiAt(view, offset, length) {
  return String.fromCharCode(...Array.from({ length }, (_, index) => view.getUint8(offset + index)))
}

const voiceAudio = await loadTurnBasedVoiceAudioModule()

test('turn-based voice downmixes and resamples browser audio to the STT sample rate', () => {
  const samples = voiceAudio.downmixAndResampleAudio([
    new Float32Array([0, 1, 0, -1]),
    new Float32Array([1, 1, 0, 0]),
  ], 8, 4)

  assert.deepEqual([...samples], [0.5, 0])
})

test('turn-based voice WAV encoder emits a mono 16-bit PCM container', () => {
  const encoded = voiceAudio.encodePcmWav(new Float32Array([-1, 0, 1]), 16_000)
  const view = new DataView(encoded)

  assert.equal(asciiAt(view, 0, 4), 'RIFF')
  assert.equal(asciiAt(view, 8, 4), 'WAVE')
  assert.equal(asciiAt(view, 12, 4), 'fmt ')
  assert.equal(asciiAt(view, 36, 4), 'data')
  assert.equal(view.getUint16(20, true), 1)
  assert.equal(view.getUint16(22, true), 1)
  assert.equal(view.getUint32(24, true), 16_000)
  assert.equal(view.getUint16(34, true), 16)
  assert.equal(view.getUint32(40, true), 6)
  assert.equal(view.getInt16(44, true), -32767)
  assert.equal(view.getInt16(46, true), 0)
  assert.equal(view.getInt16(48, true), 32767)
})
