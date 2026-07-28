import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

async function loadTrainingModeModule() {
  const sourcePath = path.resolve('src/services/trainingMode.ts')
  const source = fs.readFileSync(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  })
  const outputPath = path.join(os.tmpdir(), `training-mode-${process.pid}-${Date.now()}.mjs`)
  fs.writeFileSync(outputPath, output.outputText)
  try {
    return await import(pathToFileURL(outputPath).href)
  } finally {
    fs.rmSync(outputPath, { force: true })
  }
}

const trainingMode = await loadTrainingModeModule()

test('buildTrainingModeChatPath carries the selected training mode', () => {
  const voicePath = new URL(trainingMode.buildTrainingModeChatPath(42, 'voice'), 'http://localhost')
  const videoPath = new URL(trainingMode.buildTrainingModeChatPath(42, 'video'), 'http://localhost')

  assert.equal(voicePath.pathname, '/conversations/42')
  assert.equal(voicePath.searchParams.get('trainingMode'), 'voice')
  assert.equal(voicePath.searchParams.get('interactionMode'), 'turn_based')
  assert.equal(videoPath.pathname, '/conversations/42')
  assert.equal(videoPath.searchParams.get('trainingMode'), 'video')
  assert.equal(videoPath.searchParams.get('interactionMode'), 'turn_based')
})

test('buildTrainingModeChatPath carries realtime as interaction mode', () => {
  const path = trainingMode.buildTrainingModeChatPath(42, 'voice', null, 'realtime')
  const url = new URL(path, 'http://localhost')

  assert.equal(url.pathname, '/conversations/42')
  assert.equal(url.searchParams.get('trainingMode'), 'voice')
  assert.equal(url.searchParams.get('interactionMode'), 'realtime')
})

test('buildTrainingModeChatPath carries explicit realtime profile for realtime calls', () => {
  const path = trainingMode.buildTrainingModeChatPath(42, 'voice', 'training-session-1', 'realtime', {
    realtimeProfile: 'speech_to_speech',
  })
  const url = new URL(path, 'http://localhost')

  assert.equal(trainingMode.REALTIME_PROFILE_QUERY_PARAM, 'realtimeProfile')
  assert.equal(url.pathname, '/conversations/42')
  assert.equal(url.searchParams.get('trainingMode'), 'voice')
  assert.equal(url.searchParams.get('interactionMode'), 'realtime')
  assert.equal(url.searchParams.get('trainingSessionId'), 'training-session-1')
  assert.equal(url.searchParams.get('realtimeProfile'), 'speech_to_speech')
})

test('buildTrainingModeChatPath maps legacy realtime mode to voice plus realtime interaction', () => {
  const path = trainingMode.buildTrainingModeChatPath(42, 'realtime')
  const url = new URL(path, 'http://localhost')

  assert.equal(url.pathname, '/conversations/42')
  assert.equal(url.searchParams.get('trainingMode'), 'voice')
  assert.equal(url.searchParams.get('interactionMode'), 'realtime')
})

test('buildTrainingModeChatPath carries training mode and training session id', () => {
  const path = trainingMode.buildTrainingModeChatPath(42, 'voice', 'training-session-1')
  const url = new URL(path, 'http://localhost')

  assert.equal(url.pathname, '/conversations/42')
  assert.equal(url.searchParams.get('trainingMode'), 'voice')
  assert.equal(url.searchParams.get('trainingSessionId'), 'training-session-1')
})

test('buildTrainingModeChatPath carries live coach profile and language pair', () => {
  const path = trainingMode.buildTrainingModeChatPath(42, 'voice', 'training-session-1', 'realtime', {
    trainingProfile: 'live_coach',
    sourceLanguage: 'zh-CN',
    targetLanguage: 'en-US',
  })
  const url = new URL(path, 'http://localhost')

  assert.equal(url.pathname, '/conversations/42')
  assert.equal(url.searchParams.get('trainingMode'), 'voice')
  assert.equal(url.searchParams.get('interactionMode'), 'realtime')
  assert.equal(url.searchParams.get('trainingProfile'), 'live_coach')
  assert.equal(url.searchParams.get('sourceLanguage'), 'zh-CN')
  assert.equal(url.searchParams.get('targetLanguage'), 'en-US')
})

test('buildTrainingModeChatPath carries non-default training feedback modes', () => {
  const assistedPath = new URL(trainingMode.buildTrainingModeChatPath(42, 'voice', null, null, {
    trainingFeedbackMode: 'assisted',
  }), 'http://localhost')
  const drillPath = new URL(trainingMode.buildTrainingModeChatPath(42, 'voice', null, null, {
    trainingFeedbackMode: 'drill',
  }), 'http://localhost')

  assert.equal(trainingMode.TRAINING_FEEDBACK_MODE_QUERY_PARAM, 'trainingFeedbackMode')
  assert.equal(assistedPath.searchParams.get('trainingFeedbackMode'), 'assisted')
  assert.equal(drillPath.searchParams.get('trainingFeedbackMode'), 'drill')
})

test('buildTrainingModeChatPath carries reply language', () => {
  const path = new URL(trainingMode.buildTrainingModeChatPath(42, 'text', 'training-session-1', null, {
    replyLanguage: 'en-US',
  }), 'http://localhost')

  assert.equal(trainingMode.REPLY_LANGUAGE_QUERY_PARAM, 'replyLanguage')
  assert.equal(path.searchParams.get('replyLanguage'), 'en-US')
})

test('buildTrainingModeChatPath preserves existing URLs when feedback mode is omitted or default', () => {
  const omittedPath = new URL(trainingMode.buildTrainingModeChatPath(42, 'voice'), 'http://localhost')
  const defaultPath = new URL(trainingMode.buildTrainingModeChatPath(42, 'voice', null, null, {
    trainingFeedbackMode: 'simulation',
  }), 'http://localhost')
  const invalidPath = new URL(trainingMode.buildTrainingModeChatPath(42, 'voice', null, null, {
    trainingFeedbackMode: 'review',
  }), 'http://localhost')

  assert.equal(omittedPath.searchParams.has('trainingFeedbackMode'), false)
  assert.equal(defaultPath.searchParams.has('trainingFeedbackMode'), false)
  assert.equal(invalidPath.searchParams.has('trainingFeedbackMode'), false)
})

test('getTrainingModeFromLocation reads valid modes from query first', () => {
  assert.equal(
    trainingMode.getTrainingModeFromLocation('?trainingMode=voice', { trainingMode: 'text' }),
    'voice',
  )
  assert.equal(trainingMode.getTrainingModeFromLocation('?trainingMode=text', null), 'text')
  assert.equal(trainingMode.getTrainingModeFromLocation('?trainingMode=video', null), 'video')
  assert.equal(trainingMode.getTrainingModeFromLocation('?trainingMode=realtime', null), 'voice')
})

test('getTrainingModeFromLocation falls back to route state and rejects invalid modes', () => {
  assert.equal(
    trainingMode.getTrainingModeFromLocation('?trainingMode=invalid', { trainingMode: 'video' }),
    'video',
  )
  assert.equal(trainingMode.getTrainingModeFromLocation('', { trainingMode: 'voice' }), 'voice')
  assert.equal(trainingMode.getTrainingModeFromLocation('?trainingMode=invalid', null), null)
})

test('getInteractionModeFromLocation reads valid modes from query first', () => {
  assert.equal(
    trainingMode.getInteractionModeFromLocation('?interactionMode=realtime', { interactionMode: 'turn_based' }),
    'realtime',
  )
  assert.equal(trainingMode.getInteractionModeFromLocation('?interactionMode=turn_based', null), 'turn_based')
})

test('getInteractionModeFromLocation falls back to route state and defaults to turn based', () => {
  assert.equal(
    trainingMode.getInteractionModeFromLocation('?interactionMode=invalid', { interactionMode: 'realtime' }),
    'realtime',
  )
  assert.equal(trainingMode.getInteractionModeFromLocation('', null), 'turn_based')
  assert.equal(trainingMode.getInteractionModeFromLocation('?interactionMode=invalid', null), 'turn_based')
})

test('legacy realtime route state and query map to voice plus realtime interaction', () => {
  assert.equal(trainingMode.getTrainingModeFromLocation('?trainingMode=realtime', null), 'voice')
  assert.equal(trainingMode.getInteractionModeFromLocation('?trainingMode=realtime', null), 'realtime')
  assert.equal(trainingMode.getTrainingModeFromLocation('', { trainingMode: 'realtime' }), 'voice')
  assert.equal(trainingMode.getInteractionModeFromLocation('', { trainingMode: 'realtime' }), 'realtime')
})

test('getRealtimeProfileFromLocation reads query first and supports route state aliases', () => {
  assert.equal(
    trainingMode.getRealtimeProfileFromLocation('?realtimeProfile=speech_to_speech', {
      realtimeProfile: 'cascade',
    }),
    'speech_to_speech',
  )
  assert.equal(
    trainingMode.getRealtimeProfileFromLocation('', { realtimeProfile: 'openai_realtime' }),
    'speech_to_speech',
  )
  assert.equal(
    trainingMode.getRealtimeProfileFromLocation('', { voice_profile: 'near_realtime' }),
    'cascade',
  )
  assert.equal(trainingMode.getRealtimeProfileFromLocation('?realtimeProfile=invalid', null), null)
})

test('getTrainingSessionIdFromLocation reads query first and falls back to route state', () => {
  assert.equal(
    trainingMode.getTrainingSessionIdFromLocation('?trainingSessionId=session-from-query', {
      trainingSessionId: 'session-from-state',
    }),
    'session-from-query',
  )
  assert.equal(
    trainingMode.getTrainingSessionIdFromLocation('', { trainingSessionId: ' session-from-state ' }),
    'session-from-state',
  )
  assert.equal(trainingMode.getTrainingSessionIdFromLocation('?trainingSessionId=', null), null)
})

test('getTrainingProfileFromLocation reads query first and defaults to practice', () => {
  assert.equal(
    trainingMode.getTrainingProfileFromLocation('?trainingProfile=live_coach', { trainingProfile: 'practice' }),
    'live_coach',
  )
  assert.equal(trainingMode.getTrainingProfileFromLocation('', { trainingProfile: 'live_coach' }), 'live_coach')
  assert.equal(trainingMode.getTrainingProfileFromLocation('', { source: 'live-coach' }), 'live_coach')
  assert.equal(trainingMode.getTrainingProfileFromLocation('?trainingProfile=invalid', null), 'practice')
})

test('getTrainingFeedbackModeFromLocation reads query first and falls back to route state', () => {
  assert.equal(
    trainingMode.getTrainingFeedbackModeFromLocation('?trainingFeedbackMode=assisted', {
      trainingFeedbackMode: 'drill',
    }),
    'assisted',
  )
  assert.equal(trainingMode.getTrainingFeedbackModeFromLocation('?trainingFeedbackMode=drill', null), 'drill')
  assert.equal(
    trainingMode.getTrainingFeedbackModeFromLocation('?trainingFeedbackMode=invalid', {
      trainingFeedbackMode: 'drill',
    }),
    'drill',
  )
  assert.equal(trainingMode.getTrainingFeedbackModeFromLocation('', { trainingFeedbackMode: 'simulation' }), 'simulation')
})

test('getTrainingFeedbackModeFromLocation defaults to simulation', () => {
  assert.equal(trainingMode.getTrainingFeedbackModeFromLocation('', null), 'simulation')
  assert.equal(trainingMode.getTrainingFeedbackModeFromLocation('?trainingFeedbackMode=invalid', null), 'simulation')
})

test('getTrainingReplyLanguageFromLocation reads query first and falls back to state', () => {
  assert.equal(
    trainingMode.getTrainingReplyLanguageFromLocation('?replyLanguage=en-US', { replyLanguage: 'zh-CN' }),
    'en-US',
  )
  assert.equal(
    trainingMode.getTrainingReplyLanguageFromLocation('', { replyLanguage: ' ja ' }),
    'ja',
  )
  assert.equal(trainingMode.getTrainingReplyLanguageFromLocation('?replyLanguage=', null), null)
})

test('getLiveCoachLanguagePairFromLocation reads query first and falls back to state', () => {
  assert.deepEqual(
    trainingMode.getLiveCoachLanguagePairFromLocation(
      '?sourceLanguage=zh-CN&targetLanguage=en-US',
      { sourceLanguage: 'ja-JP', targetLanguage: 'ko-KR' },
    ),
    { sourceLanguage: 'zh-CN', targetLanguage: 'en-US' },
  )
  assert.deepEqual(
    trainingMode.getLiveCoachLanguagePairFromLocation('', {
      sourceLanguage: ' ja-JP ',
      targetLanguage: ' ko-KR ',
    }),
    { sourceLanguage: 'ja-JP', targetLanguage: 'ko-KR' },
  )
  assert.deepEqual(
    trainingMode.getLiveCoachLanguagePairFromLocation('?sourceLanguage=&targetLanguage=', null),
    { sourceLanguage: null, targetLanguage: null },
  )
})

test('live coach language helpers preserve complex BCP-47 tags', () => {
  const path = trainingMode.buildTrainingModeChatPath(42, 'voice', 'training-session-1', 'realtime', {
    trainingProfile: 'live_coach',
    sourceLanguage: 'zh-Hant-TW',
    targetLanguage: 'pt-BR',
  })
  const url = new URL(path, 'http://localhost')

  assert.equal(url.searchParams.get('sourceLanguage'), 'zh-Hant-TW')
  assert.equal(url.searchParams.get('targetLanguage'), 'pt-BR')
  assert.deepEqual(
    trainingMode.getLiveCoachLanguagePairFromLocation('?sourceLanguage=ar-SA&targetLanguage=es-419', null),
    { sourceLanguage: 'ar-SA', targetLanguage: 'es-419' },
  )
})

test('isTrainingModeBattlePrep gates voice and video battle prep modes', () => {
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'voice', 'voice'), true)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'video', 'video'), true)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'realtime', 'realtime'), true)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'voice', 'voice', 'realtime', 'realtime'), true)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'video', 'voice'), false)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'voice', 'realtime'), false)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'voice', 'voice', 'turn_based', 'realtime'), false)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', 'text', 'video'), false)
  assert.equal(trainingMode.isTrainingModeBattlePrep('private', 'voice', 'voice'), false)
  assert.equal(trainingMode.isTrainingModeBattlePrep('battle_prep', null, 'voice'), false)
})
