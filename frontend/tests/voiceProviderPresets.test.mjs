import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadVoiceProviderPresetsModule() {
  const sourcePath = path.resolve('src/services/voiceProviderPresets.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(os.tmpdir(), `voice-provider-presets-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

test('voice provider presets include default URLs and no API keys', async () => {
  const presets = await loadVoiceProviderPresetsModule()
  const minimax = presets.providerPresetByValue('tts', 'minimax')
  const elevenlabs = presets.providerPresetByValue('tts', 'elevenlabs')
  const deepgram = presets.providerPresetByValue('stt', 'deepgram')
  const openaiRealtime = presets.providerPresetByValue('realtime', 'openai')
  const geminiLive = presets.providerPresetByValue('realtime', 'google.gemini_live')
  const ultravox = presets.providerPresetByValue('realtime', 'ultravox.realtime')

  assert.equal(minimax.baseUrl, 'https://api.minimax.chat')
  assert.equal(elevenlabs.baseUrl, 'https://api.elevenlabs.io')
  assert.equal(deepgram.baseUrl, 'https://api.deepgram.com/v1')
  assert.equal(deepgram.status, 'inventory')
  assert.equal(openaiRealtime.model, 'gpt-realtime-2.1')
  assert.equal(openaiRealtime.realtimeTranscriptionModel, 'gpt-realtime-whisper')
  assert.equal(geminiLive.status, 'inventory')
  assert.equal(geminiLive.model, 'gemini-live-2.5-flash-preview')
  assert.equal(ultravox.baseUrl, 'https://api.ultravox.ai/api/')
  assert.equal(ultravox.model, 'fixie-ai/ultravox')

  const serialized = JSON.stringify({
    llm: presets.LLM_PROVIDER_PRESETS,
    stt: presets.STT_PROVIDER_PRESETS,
    tts: presets.TTS_PROVIDER_PRESETS,
    realtime: presets.REALTIME_PROVIDER_PRESETS,
  }).toLowerCase()
  assert.equal(serialized.includes('api_key'), false)
  assert.equal(serialized.includes('apikey'), false)
  assert.equal(serialized.includes('sk-'), false)
})
