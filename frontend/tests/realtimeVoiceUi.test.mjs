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

test('ChatInput places realtime voice controls inside the message input bar', () => {
  const source = readSource('src/components/chat/ChatInput.tsx')
  const css = readSource('src/components/chat/ChatInput.css')
  const textareaIndex = source.indexOf('<Textarea')
  const realtimeIndex = source.indexOf('{realtimeVoiceControl}')
  const voiceIndex = source.indexOf('{roomId && showVoiceButton')
  const videoIndex = source.indexOf('{showVideoButton &&')

  assert.match(source, /realtimeVoiceControl\?: React\.ReactNode/)
  assert.notEqual(textareaIndex, -1)
  assert.notEqual(realtimeIndex, -1)
  assert.notEqual(voiceIndex, -1)
  assert.notEqual(videoIndex, -1)
  assert.ok(textareaIndex < realtimeIndex)
  assert.ok(realtimeIndex < voiceIndex)
  assert.ok(realtimeIndex < videoIndex)
  assert.doesNotMatch(source, /message-input-realtime-slot/)
  assert.match(css, /\.message-input-bar \.realtime-voice-recorder/)
  assert.match(css, /\.message-input-bar \.realtime-voice-status\s*\{[\s\S]*display: none/)
  assert.doesNotMatch(css, /realtime-voice-action-label[\s\S]*display:\s*none/)
  assert.doesNotMatch(css, /message-input-realtime-slot/)
})

test('Bottom voice controls keep text labels across realtime and turn-based modes', () => {
  const voiceRecorder = readSource('src/components/VoiceRecorder.tsx')
  const realtimeRecorder = readSource('src/components/RealtimeVoiceRecorder.tsx')
  const voiceCss = readSource('src/components/VoiceRecorder.css')
  const chatInputCss = readSource('src/components/chat/ChatInput.css')

  assert.match(voiceRecorder, /const actionLabel = state === 'idle'[\s\S]*'Voice reply'/)
  assert.match(voiceRecorder, /<span className="voice-btn-label">\{actionLabel\}<\/span>/)
  assert.match(realtimeRecorder, /className="realtime-voice-action-label"/)
  assert.match(voiceCss, /\.voice-btn\s*\{[\s\S]*min-width: 84px[\s\S]*border-radius: 999px/)
  assert.match(chatInputCss, /\.message-input-bar \.voice-btn,[\s\S]*\.message-input-bar \.realtime-voice-action\s*\{[\s\S]*width: auto/)
  assert.doesNotMatch(chatInputCss, /realtime-voice-action-label[\s\S]*display:\s*none/)
})

test('ChatPage keeps voice and video controls mode-specific in ChatInput', () => {
  const source = readSource('src/pages/ChatPage.tsx')
  const voiceBarIndex = source.indexOf('data-testid="voice-practice-bar"')
  const realtimeBarIndex = source.indexOf('data-testid="realtime-practice-bar"')
  const videoBarIndex = source.indexOf('data-testid="video-practice-bar"')
  const voiceBarSource = source.slice(voiceBarIndex, realtimeBarIndex)
  const realtimeBarSource = source.slice(realtimeBarIndex, videoBarIndex)

  assert.notEqual(voiceBarIndex, -1)
  assert.notEqual(realtimeBarIndex, -1)
  assert.notEqual(videoBarIndex, -1)
  assert.match(source, /const realtimeVoiceControl = isRealtimeBattlePrep \? \(/)
  assert.match(source, /realtimeVoiceControl=\{realtimeVoiceControl\}/)
  assert.match(source, /showVoiceButton=\{!isRealtimeBattlePrep && !isVideoBattlePrep\}/)
  assert.match(source, /showVideoButton=\{isVideoBattlePrep\}/)
  assert.doesNotMatch(source, /voiceStatusControl/)
  assert.doesNotMatch(source, /message-input-turn-voice/)
  assert.match(voiceBarSource, /voice-call-wave training-voice-wave/)
  assert.match(voiceBarSource, /voice-call-action/)
  assert.doesNotMatch(voiceBarSource, /<VoiceRecorder/)
  assert.doesNotMatch(realtimeBarSource, /<RealtimeVoiceRecorder/)
  assert.doesNotMatch(source, /data-testid="training-voice-panel"/)
})

test('Realtime voice status bar shows activity state and mic wave, not latest reply text', () => {
  const source = readSource('src/pages/ChatPage.tsx')
  const css = readSource('src/pages/ChatPage.css')

  assert.match(source, /REALTIME_STATUS_WAVE_BARS/)
  assert.match(source, /const realtimeBarCopy = realtimeRecorderError/)
  assert.match(source, /realtimeUserIsSpeaking/)
  assert.match(source, /voice-activity-wave realtime-call-wave/)
  assert.match(source, /voice-activity-wave voice-call-wave training-voice-wave/)
  assert.match(source, /height: `\$\{4 \+ Math\.round\(18 \* realtimeWaveLevel \* scale\)\}px`/)
  assert.match(source, /animationDelay: `\$\{index \* 38\}ms`/)
  assert.match(source, /onRecorderStatusChange=\{handleRealtimeRecorderStatusChange\}/)
  assert.match(source, /onInputLevelChange=\{handleRealtimeInputLevelChange\}/)
  assert.doesNotMatch(source, /latestPersonaPrompt \|\| tr/)
  assert.match(css, /\.chat-page-realtime-call-bar \.realtime-call-copy > span/)
  assert.match(css, /\.voice-activity-wave span/)
  assert.match(css, /\.realtime-call-wave/)
  assert.match(css, /\.voice-activity-wave\.active span,[\s\S]*\.training-voice-wave\.listening span,[\s\S]*\.training-voice-wave\.speaking span[\s\S]*animation: voice-activity-wave-pulse 820ms ease-in-out infinite alternate/)
  assert.match(css, /@keyframes voice-activity-wave-pulse/)
  assert.doesNotMatch(css, /\.chat-page-realtime-call-bar span\s*\{/)
})

test('RealtimeVoiceRecorder handles payload transcript text and user final transcript callbacks', () => {
  const source = readSource('src/components/RealtimeVoiceRecorder.tsx')

  assert.match(source, /function transcriptTextFromEvent/)
  assert.match(source, /textValue\(payload\.text\)/)
  assert.match(source, /onFinalTranscript\?\.\(content, role\)/)
  assert.doesNotMatch(source, /event\.type === 'transcript\.done' && event\.text\.trim\(\)/)
  assert.doesNotMatch(source, /setPreview\(event\.text\.trim\(\)\)/)
})

test('RealtimeVoiceRecorder reports status and local microphone input level', () => {
  const source = readSource('src/components/RealtimeVoiceRecorder.tsx')

  assert.match(source, /onRecorderStatusChange\?: \(status: RealtimeSessionStatus, error: string \| null\) => void/)
  assert.match(source, /onInputLevelChange\?: \(level: number\) => void/)
  assert.match(source, /function inputLevelFromSamples/)
  assert.match(source, /onRecorderStatusChange\?\.\(status, error\)/)
  assert.match(source, /emitInputLevel\(inputLevelFromSamples\(input\)\)/)
  assert.match(source, /onInputLevelChange\?\.\(rounded\)/)
  assert.match(source, /resetInputLevel\(\)/)
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

test('Settings marks Volcengine Doubao Realtime as backend runtime', () => {
  const settings = readSource('src/pages/SettingsPage.tsx')
  const presets = readSource('src/services/voiceProviderPresets.ts')
  const providerStart = presets.indexOf("value: 'volcengine.doubao_realtime'")
  const providerEnd = presets.indexOf('},', providerStart)
  const doubaoRealtimePreset = presets.slice(providerStart, providerEnd)

  assert.notEqual(providerStart, -1)
  assert.notEqual(providerEnd, -1)
  assert.match(doubaoRealtimePreset, /status: 'runtime'/)
  assert.doesNotMatch(doubaoRealtimePreset, /status: 'inventory'/)
  assert.match(doubaoRealtimePreset, /backend Volcengine Doubao realtime runtime/)
  assert.match(settings, /preset\.status === 'inventory'/)
  assert.match(settings, /non-runtime providers stay adapter pending/)
})

test('ChatPage waits for persisted realtime transcript messages instead of optimistic bubbles', () => {
  const source = readSource('src/pages/ChatPage.tsx')

  assert.match(source, /OPTIMISTIC_REALTIME_TRANSCRIPT_SOURCE/)
  assert.match(source, /nextMessages\[optimisticIndex\] = message/)
  assert.match(source, /onFinalTranscript=\{handleRealtimeTranscriptFinal\}/)
  assert.match(source, /onPersistedTranscript=\{handleRealtimeTranscriptPersisted\}/)
  assert.match(source, /appendRealtimeTranscriptMessage\(message\)/)
  assert.doesNotMatch(source, /const appendOptimisticRealtimeTranscriptMessage/)
  assert.doesNotMatch(source, /optimisticRealtimeMessageIdRef/)
})

test('useChat replaces optimistic realtime transcript messages from room SSE', () => {
  const source = readSource('src/hooks/useChat.ts')

  assert.match(source, /OPTIMISTIC_REALTIME_TRANSCRIPT_SOURCE = 'realtime_voice_final'/)
  assert.match(source, /function replaceOptimisticRealtimeTranscriptMessage/)
  assert.match(source, /isOptimisticRealtimeTranscriptMessage\(item\)/)
  assert.match(source, /isSameVisibleRealtimeTranscriptMessage\(message, item\)/)
  assert.match(source, /nextMessages\[optimisticIndex\] = message/)
  assert.match(source, /replaceOptimisticRealtimeTranscriptMessage\(prev\.messages, msg\)/)
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
