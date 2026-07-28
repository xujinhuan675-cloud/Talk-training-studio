import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

async function loadRealtimeSessionModule() {
  const sourcePath = path.resolve('src/services/realtimeSession.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const outputText = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const outputPath = path.join(os.tmpdir(), `realtime-session-ui-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

function sourceObjectBlock(source, marker) {
  const start = source.indexOf(marker)
  assert.notEqual(start, -1, `${marker} should exist`)
  const next = source.indexOf('\n  {', start + marker.length)
  return source.slice(start, next === -1 ? undefined : next)
}

globalThis.window = {
  location: {
    protocol: 'https:',
    host: 'demo.example',
  },
}
globalThis.atob ??= (value) => Buffer.from(value, 'base64').toString('binary')

const realtimeSession = await loadRealtimeSessionModule()

test('ChatInput exposes a bottom realtime voice control slot', () => {
  const source = readSource('src/components/chat/ChatInput.tsx')
  const css = readSource('src/components/chat/ChatInput.css')

  assert.match(source, /realtimeVoiceControl\?: React\.ReactNode/)
  assert.match(source, /message-input-realtime-slot/)
  assert.match(css, /\.message-input-realtime-slot \.realtime-voice-recorder/)
  assert.match(css, /flex: 0 0 78px/)
})

test('ChatPage moves realtime voice controls from the top mode bar into ChatInput', () => {
  const source = readSource('src/pages/ChatPage.tsx')
  const realtimeBarIndex = source.indexOf('data-testid="realtime-practice-bar"')
  const videoBarIndex = source.indexOf('data-testid="video-practice-bar"')
  const realtimeBarSource = source.slice(realtimeBarIndex, videoBarIndex)

  assert.match(source, /const realtimeVoiceControl = isRealtimeBattlePrep \? \(/)
  assert.match(source, /realtimeVoiceControl=\{realtimeVoiceControl\}/)
  assert.doesNotMatch(realtimeBarSource, /<RealtimeVoiceRecorder/)
})

test('RealtimeVoiceRecorder handles payload transcript text and user final transcript callbacks', () => {
  const source = readSource('src/components/RealtimeVoiceRecorder.tsx')

  assert.match(source, /function transcriptTextFromEvent/)
  assert.match(source, /textValue\(payload\.text\)/)
  assert.match(source, /onFinalTranscript\?\.\(content, role\)/)
  assert.doesNotMatch(source, /event\.type === 'transcript\.done' && event\.text\.trim\(\)/)
  assert.doesNotMatch(source, /setPreview\(event\.text\.trim\(\)\)/)
})

test('Realtime websocket provider follows runtime provider instead of hardcoded pipecat', () => {
  const service = readSource('src/services/realtimeSession.ts')
  const recorder = readSource('src/components/RealtimeVoiceRecorder.tsx')

  assert.match(service, /export function resolveTrainingRealtimeWebSocketProvider/)
  assert.match(service, /OPENAI_PIPECAT_REALTIME_ALIASES/)
  assert.match(service, /params\.set\('provider', resolveTrainingRealtimeWebSocketProvider\(provider\)\)/)
  assert.doesNotMatch(service, /params\.set\('provider', 'pipecat'\)/)
  assert.match(recorder, /realtimeProvider\?: string \| null/)
  assert.match(recorder, /fetchVoiceConfig/)
  assert.match(recorder, /const realtimeRuntimeProvider = resolveTrainingRealtimeWebSocketProvider\(configuredRealtimeProvider\)/)
  assert.match(recorder, /getTrainingRealtimeWebSocketUrl\(\{[\s\S]*provider: realtimeRuntimeProvider/)
  assert.match(recorder, /provider: runtimeProvider/)
  assert.doesNotMatch(recorder, /provider: 'pipecat'/)
})

test('Settings keeps Volcengine Doubao Realtime inventory with key-configured pending copy', () => {
  const settings = readSource('src/pages/SettingsPage.tsx')
  const presets = readSource('src/services/voiceProviderPresets.ts')
  const providerStart = presets.indexOf("value: 'volcengine.doubao_realtime'")
  const providerEnd = presets.indexOf('},', providerStart)
  const doubaoRealtimePreset = presets.slice(providerStart, providerEnd)

  assert.notEqual(providerStart, -1)
  assert.notEqual(providerEnd, -1)
  assert.match(doubaoRealtimePreset, /status: 'inventory'/)
  assert.doesNotMatch(doubaoRealtimePreset, /status: 'runtime'/)
  assert.match(doubaoRealtimePreset, /Volcengine realtime runtime adapter is still pending/)
  assert.match(settings, /Key configured; Realtime runtime adapter pending\./)
  assert.match(settings, /config\?\.realtime_effective_api_key_configured/)
  assert.match(settings, /preset\.status === 'inventory'/)
  assert.match(settings, /non-runtime providers stay adapter pending/)
})

test('ChatPage replaces optimistic realtime user transcripts with persisted messages', () => {
  const source = readSource('src/pages/ChatPage.tsx')

  assert.match(source, /OPTIMISTIC_REALTIME_TRANSCRIPT_SOURCE/)
  assert.match(source, /appendOptimisticRealtimeTranscriptMessage/)
  assert.match(source, /nextMessages\[optimisticIndex\] = message/)
  assert.match(source, /onFinalTranscript=\{handleRealtimeTranscriptFinal\}/)
})

test('getTrainingRealtimeWebSocketUrl uses the selected realtime provider', () => {
  const url = realtimeSession.getTrainingRealtimeWebSocketUrl({
    sessionId: 'session 1',
    roomId: 42,
    provider: 'volcengine.doubao_realtime',
    audioFormat: 'pcm16',
  })

  assert.equal(
    url,
    'wss://demo.example/api/v1/training-studio/realtime?session_id=session+1&room_id=42&provider=volcengine.doubao_realtime&audio_format=pcm16',
  )
  assert.doesNotMatch(url, /provider=pipecat/)
})

test('Settings copy distinguishes Volcengine realtime runtime from inventory-only presets', () => {
  const presets = readSource('src/services/voiceProviderPresets.ts')
  const settings = readSource('src/pages/SettingsPage.tsx')
  const doubaoPreset = sourceObjectBlock(presets, "value: 'volcengine.doubao_realtime'")
  const hasRuntimeStatus = /status:\s*'runtime'/.test(doubaoPreset)
  const hasExplicitPendingRuntimeCopy = (
    /密钥已配置，Realtime runtime 待接入/.test(`${doubaoPreset}\n${settings}`)
    || /key configured,\s*Realtime runtime pending/i.test(`${doubaoPreset}\n${settings}`)
    || /Realtime runtime 待接入/.test(`${doubaoPreset}\n${settings}`)
  )

  assert.ok(
    hasRuntimeStatus || hasExplicitPendingRuntimeCopy,
    'Volcengine Doubao Realtime must be a runtime preset or show explicit runtime-pending copy',
  )
  assert.doesNotMatch(doubaoPreset, /Inventory only until/)
  assert.doesNotMatch(settings, /Pipecat session for continuous audio, interruption, and realtime output/)
  assert.doesNotMatch(settings, /inside the Pipecat pipeline/)
})
