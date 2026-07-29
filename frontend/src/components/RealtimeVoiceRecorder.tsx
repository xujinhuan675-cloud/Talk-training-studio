import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Mic, Square } from 'lucide-react'
import {
  createRealtimeSession,
  getRealtimeVoiceAudioContract,
  getTrainingRealtimeWebSocketUrl,
  resolveTrainingRealtimeWebSocketProvider,
  RealtimeAudioOutputQueue,
  type RealtimeServerEvent,
  type RealtimeSession,
  type RealtimeAudioOutputEvent,
  type RealtimePersistedTranscriptMessage,
  type RealtimeSessionStatus,
  type RealtimeTranscriptRole,
  type RealtimeVoiceProfile,
} from '../services/realtimeSession'
import { logRealtimeClientEvent, type ClientRealtimeEventInput } from '../services/clientEventLogger'
import type { Message as ChatMessage } from '../services/api'
import { fetchVoiceConfig } from '../services/voiceConfig'
import { useI18n } from '../i18n'
import { Button } from './ui/button'

export interface RealtimeVoiceRecorderProps {
  roomId: number | null
  trainingSessionId: string | null
  disabled?: boolean
  personaId?: string | null
  counterpartName?: string
  realtimeProfile?: RealtimeVoiceProfile | null
  realtimeProvider?: string | null
  transcriptMetadata?: Record<string, unknown>
  onFinalTranscript?: (text: string, role: RealtimeTranscriptRole) => void
  onPersistedTranscript?: (text: string, role: RealtimeTranscriptRole, message?: ChatMessage) => void
  onRecorderStatusChange?: (status: RealtimeSessionStatus, error: string | null) => void
  onInputLevelChange?: (level: number) => void
}

function statusLabel(
  status: RealtimeSessionStatus,
  error: string | null,
  tr: (zhText: string, enText: string) => string,
): string {
  if (error) return error
  if (status === 'processing') return tr('正在整理你的回答', 'Processing your turn')
  if (status === 'connecting' || status === 'preparing') return tr('正在连接实时语音教练', 'Connecting realtime voice agent')
  if (status === 'speaking') return tr('AI 正在说话', 'AI is speaking')
  if (status === 'listening' || status === 'connected') return tr('实时语音教练已连接', 'Realtime voice agent connected')
  if (status === 'error') return tr('实时语音教练出错', 'Realtime voice agent error')
  if (status === 'closed') return tr('实时语音教练已停止', 'Realtime voice agent stopped')
  return tr('实时语音教练已就绪', 'Realtime voice agent ready')
}

function cleanMimeType(mimeType?: string): string {
  return mimeType?.split(';')[0]?.trim().toLowerCase() || ''
}

function isPcmAudioOutput(event: RealtimeAudioOutputEvent): boolean {
  const mimeType = cleanMimeType(event.mimeType)
  return mimeType === 'audio/pcm' || mimeType === 'audio/l16' || mimeType === 'audio/x-pcm' || mimeType === 'audio/raw'
}

function createAudioContext(): AudioContext {
  const AudioContextConstructor = window.AudioContext
    || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioContextConstructor) {
    throw new Error('Web Audio is unavailable')
  }
  return new AudioContextConstructor()
}

function createPcm16AudioBuffer(context: AudioContext, event: RealtimeAudioOutputEvent): AudioBuffer {
  const channels = Math.max(1, Math.floor(event.channels || 1))
  const sampleRate = Math.max(1, Math.floor(event.sampleRate || 24000))
  const bytesPerSample = 2
  const frameCount = Math.floor(event.audio.byteLength / (bytesPerSample * channels))
  const audioBuffer = context.createBuffer(channels, frameCount, sampleRate)
  if (frameCount === 0) return audioBuffer

  const dataView = new DataView(event.audio)
  for (let channel = 0; channel < channels; channel += 1) {
    const channelData = audioBuffer.getChannelData(channel)
    for (let frame = 0; frame < frameCount; frame += 1) {
      const byteOffset = ((frame * channels) + channel) * bytesPerSample
      channelData[frame] = Math.max(-1, Math.min(1, dataView.getInt16(byteOffset, true) / 32768))
    }
  }
  return audioBuffer
}

function encodePcm16Mono(input: Float32Array, inputSampleRate: number, outputSampleRate = 16000): ArrayBuffer {
  const sampleRate = Math.max(1, Math.floor(inputSampleRate || outputSampleRate))
  const ratio = sampleRate / outputSampleRate
  const frameCount = Math.max(1, Math.floor(input.length / ratio))
  const buffer = new ArrayBuffer(frameCount * 2)
  const view = new DataView(buffer)

  for (let frame = 0; frame < frameCount; frame += 1) {
    const start = Math.floor(frame * ratio)
    const end = Math.min(input.length, Math.floor((frame + 1) * ratio))
    let sum = 0
    let samples = 0
    for (let index = start; index < end; index += 1) {
      sum += input[index]
      samples += 1
    }
    const normalized = samples > 0 ? sum / samples : input[Math.min(start, input.length - 1)] || 0
    const clamped = Math.max(-1, Math.min(1, normalized))
    view.setInt16(frame * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
  }

  return buffer
}

function inputLevelFromSamples(input: Float32Array): number {
  if (input.length === 0) return 0
  let sum = 0
  for (let index = 0; index < input.length; index += 1) {
    const sample = input[index]
    sum += sample * sample
  }
  const rms = Math.sqrt(sum / input.length)
  return Math.max(0, Math.min(1, rms * 8))
}

function realtimeRoleFromValue(value: unknown, fallback: RealtimeTranscriptRole = 'user'): RealtimeTranscriptRole {
  const normalized = typeof value === 'string' ? value.trim().toLowerCase() : ''
  if (normalized === 'persona' || normalized === 'assistant' || normalized === 'counterpart' || normalized === 'ai') {
    return 'assistant'
  }
  if (normalized === 'user' || normalized === 'learner' || normalized === 'participant') return 'user'
  return fallback
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function textValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function eventPayload(event: RealtimeServerEvent): Record<string, unknown> {
  const payload = (event as { payload?: unknown }).payload
  return isRecord(payload) ? payload : {}
}

function transcriptTextFromEvent(event: RealtimeServerEvent): string {
  const payload = eventPayload(event)
  return textValue((event as { text?: unknown }).text)
    || textValue(payload.text)
    || textValue(payload.transcript)
}

function transcriptRoleFromEvent(
  event: RealtimeServerEvent,
  fallback: RealtimeTranscriptRole = 'user',
): RealtimeTranscriptRole {
  const payload = eventPayload(event)
  const directRole = realtimeRoleFromValue((event as { role?: unknown }).role, fallback)
  if (directRole !== fallback || textValue((event as { role?: unknown }).role)) return directRole
  const payloadRole = realtimeRoleFromValue(payload.role, fallback)
  if (payloadRole !== fallback || textValue(payload.role)) return payloadRole
  const eventType = textValue(payload.eventType || (event as { eventType?: unknown }).eventType)
  return eventType.startsWith('response.') ? 'assistant' : fallback
}

function realtimeEventKey(
  event: RealtimeServerEvent,
  role: RealtimeTranscriptRole,
  content: string,
  prefix: string,
): string {
  const payload = eventPayload(event)
  const stableId = textValue(payload.eventId)
    || textValue(payload.event_id)
    || textValue(payload.itemId)
    || textValue(payload.item_id)
    || textValue(payload.responseId)
    || textValue(payload.response_id)
    || textValue((event as { createdAt?: unknown }).createdAt)
  return stableId ? `${prefix}:${stableId}` : `${prefix}:${role}:${content}`
}

function normalizedSenderType(value: unknown, role: RealtimeTranscriptRole): ChatMessage['sender_type'] {
  const normalized = typeof value === 'string' ? value.trim().toLowerCase() : ''
  if (normalized === 'persona' || normalized === 'assistant') return 'persona'
  if (normalized === 'system') return 'system'
  return role === 'assistant' ? 'persona' : 'user'
}

function realtimeMessageToChatMessage(
  message: RealtimePersistedTranscriptMessage,
  role: RealtimeTranscriptRole,
  createdAt?: string,
): ChatMessage | null {
  const id = Number(message.id)
  const roomId = Number(message.room_id)
  const content = typeof message.content === 'string' ? message.content.trim() : ''
  if (!Number.isFinite(id) || !Number.isFinite(roomId) || !content) return null

  const senderType = normalizedSenderType(message.sender_type, role)
  const senderId = typeof message.sender_id === 'string' && message.sender_id.trim()
    ? message.sender_id.trim()
    : senderType === 'persona'
      ? 'assistant'
      : senderType
  const chatMessage: ChatMessage = {
    id,
    room_id: roomId,
    sender_type: senderType,
    sender_id: senderId,
    content,
    timestamp: typeof message.timestamp === 'string' || message.timestamp === null
      ? message.timestamp
      : createdAt || null,
    emotion_score: typeof message.emotion_score === 'number' && Number.isFinite(message.emotion_score)
      ? message.emotion_score
      : null,
    emotion_label: typeof message.emotion_label === 'string' ? message.emotion_label : null,
  }
  if (isRecord(message.metadata)) chatMessage.metadata = message.metadata
  if (Array.isArray(message.attachments)) chatMessage.attachments = message.attachments
  if (typeof message.video_url === 'string') chatMessage.video_url = message.video_url
  if (typeof message.videoUrl === 'string') chatMessage.videoUrl = message.videoUrl
  if (typeof message.mediaUrl === 'string') chatMessage.mediaUrl = message.mediaUrl
  if (typeof message.media_url === 'string') chatMessage.media_url = message.media_url
  return chatMessage
}

function persistedTranscriptMessageFromEvent(event: RealtimeServerEvent): RealtimePersistedTranscriptMessage | null {
  const payload = eventPayload(event)
  const value = payload.message ?? (event as { message?: unknown }).message
  return isRecord(value) ? value as unknown as RealtimePersistedTranscriptMessage : null
}

function realtimeRoleFromPersistedMessage(
  message: RealtimePersistedTranscriptMessage,
  fallback: RealtimeTranscriptRole,
): RealtimeTranscriptRole {
  const metadata = isRecord(message.metadata) ? message.metadata : null
  const realtime = isRecord(metadata?.realtime) ? metadata.realtime : null
  return realtimeRoleFromValue(message.sender_type || realtime?.role, fallback)
}

function errorName(error: unknown): string | undefined {
  return error instanceof Error && error.name ? error.name : undefined
}

function isMicrophonePermissionError(error: unknown): boolean {
  const name = errorName(error)
  return name === 'NotAllowedError' || name === 'PermissionDeniedError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function cleanRealtimeProvider(value?: string | null): string | null {
  const normalized = value?.trim()
  return normalized || null
}

type RecorderClientRealtimeEventInput =
  Omit<ClientRealtimeEventInput, 'trainingSessionId' | 'roomId' | 'provider' | 'realtimeProfile'>
  & {
    provider?: string | null
    configuredRealtimeProvider?: string | null
  }

export default function RealtimeVoiceRecorder({
  roomId,
  trainingSessionId,
  disabled,
  personaId,
  counterpartName,
  realtimeProfile,
  realtimeProvider,
  transcriptMetadata,
  onFinalTranscript,
  onPersistedTranscript,
  onRecorderStatusChange,
  onInputLevelChange,
}: RealtimeVoiceRecorderProps) {
  const { tr } = useI18n()
  const realtimeSessionRef = useRef<RealtimeSession | null>(null)
  const localStreamRef = useRef<MediaStream | null>(null)
  const inputAudioContextRef = useRef<AudioContext | null>(null)
  const inputAudioSourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const inputAudioProcessorRef = useRef<ScriptProcessorNode | null>(null)
  const inputAudioSilenceRef = useRef<GainNode | null>(null)
  const outputAudioQueueRef = useRef<RealtimeAudioOutputQueue | null>(null)
  const outputAudioElementRef = useRef<HTMLAudioElement | null>(null)
  const outputAudioUrlRef = useRef<string | null>(null)
  const outputAudioContextRef = useRef<AudioContext | null>(null)
  const outputAudioSourceRef = useRef<AudioBufferSourceNode | null>(null)
  const transcriptKeysRef = useRef<Set<string>>(new Set())
  const inputSendErrorLoggedRef = useRef(false)
  const startFailureLoggedRef = useRef(false)
  const savedRealtimeProviderRef = useRef<string | null>(null)
  const activeRealtimeProviderRef = useRef<string | null>(null)
  const inputLevelRef = useRef(0)
  const inputLevelEmitAtRef = useRef(0)
  const inputLevelEmitValueRef = useRef(0)
  const [status, setStatus] = useState<RealtimeSessionStatus>('idle')
  const [preview, setPreview] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    onRecorderStatusChange?.(status, error)
  }, [error, onRecorderStatusChange, status])

  const fallbackRealtimeProvider = resolveTrainingRealtimeWebSocketProvider(realtimeProvider)

  const loadConfiguredRealtimeProvider = useCallback(async (): Promise<string | null> => {
    const providerFromProps = cleanRealtimeProvider(realtimeProvider)
    if (providerFromProps) return providerFromProps
    if (savedRealtimeProviderRef.current) return savedRealtimeProviderRef.current
    try {
      const voiceConfig = await fetchVoiceConfig()
      const savedProvider = cleanRealtimeProvider(voiceConfig.realtime_provider)
      savedRealtimeProviderRef.current = savedProvider
      return savedProvider
    } catch {
      return null
    }
  }, [realtimeProvider])

  const logClientEvent = useCallback((event: RecorderClientRealtimeEventInput) => {
    const {
      provider,
      configuredRealtimeProvider,
      payload,
      ...eventFields
    } = event
    const runtimeProvider = provider
      || activeRealtimeProviderRef.current
      || fallbackRealtimeProvider
    const configuredProvider = configuredRealtimeProvider
      || cleanRealtimeProvider(realtimeProvider)
      || savedRealtimeProviderRef.current
    const providerPayload = configuredProvider && configuredProvider !== runtimeProvider
      ? {
          configuredRealtimeProvider: configuredProvider,
          runtimeProvider,
        }
      : {}
    void logRealtimeClientEvent({
      trainingSessionId,
      roomId,
      provider: runtimeProvider,
      realtimeProfile: realtimeProfile || undefined,
      ...eventFields,
      payload: {
        ...(payload || {}),
        ...providerPayload,
      },
    })
  }, [fallbackRealtimeProvider, realtimeProfile, realtimeProvider, roomId, trainingSessionId])

  const resetInputLevel = useCallback(() => {
    inputLevelRef.current = 0
    inputLevelEmitAtRef.current = 0
    inputLevelEmitValueRef.current = 0
    onInputLevelChange?.(0)
  }, [onInputLevelChange])

  const emitInputLevel = useCallback((level: number) => {
    const previous = inputLevelRef.current
    const smoothed = level > previous
      ? previous * 0.35 + level * 0.65
      : previous * 0.78 + level * 0.22
    inputLevelRef.current = smoothed
    const rounded = Math.round(smoothed * 100) / 100
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
    if (
      now - inputLevelEmitAtRef.current < 80
      && Math.abs(rounded - inputLevelEmitValueRef.current) < 0.04
    ) {
      return
    }
    inputLevelEmitAtRef.current = now
    inputLevelEmitValueRef.current = rounded
    onInputLevelChange?.(rounded)
  }, [onInputLevelChange])

  const stopOutputAudio = useCallback(() => {
    outputAudioQueueRef.current?.clear()
    try {
      outputAudioSourceRef.current?.stop()
    } catch {
      // Source may already have ended.
    }
    outputAudioSourceRef.current = null
    if (outputAudioElementRef.current) {
      outputAudioElementRef.current.pause()
      outputAudioElementRef.current.removeAttribute('src')
      outputAudioElementRef.current.load()
    }
    outputAudioElementRef.current = null
    if (outputAudioUrlRef.current) {
      URL.revokeObjectURL(outputAudioUrlRef.current)
      outputAudioUrlRef.current = null
    }
  }, [])

  const closeRealtime = useCallback((nextStatus: RealtimeSessionStatus = 'closed') => {
    const realtimeSession = realtimeSessionRef.current
    const closingRealtimeProvider = activeRealtimeProviderRef.current || fallbackRealtimeProvider
    const committedAudio = Boolean(realtimeSession?.isConnected)
    const hadRealtimeState = Boolean(
      realtimeSession
      || localStreamRef.current
      || inputAudioContextRef.current
      || outputAudioContextRef.current,
    )
    stopOutputAudio()
    resetInputLevel()
    inputAudioProcessorRef.current?.disconnect()
    inputAudioProcessorRef.current = null
    inputAudioSourceRef.current?.disconnect()
    inputAudioSourceRef.current = null
    inputAudioSilenceRef.current?.disconnect()
    inputAudioSilenceRef.current = null
    realtimeSessionRef.current = null
    if (realtimeSession) {
      try {
        if (realtimeSession.isConnected) {
          realtimeSession.send({ type: 'audio.commit' })
        }
      } catch {
        // The pipeline may already have closed; close still tears down local state.
      }
      try {
        realtimeSession.close(nextStatus)
      } catch {
        // Socket close can race with a backend close event.
      }
    }
    localStreamRef.current?.getTracks().forEach((track) => track.stop())
    localStreamRef.current = null
    void inputAudioContextRef.current?.close().catch(() => {})
    inputAudioContextRef.current = null
    void outputAudioContextRef.current?.close().catch(() => {})
    outputAudioContextRef.current = null
    setStatus(nextStatus)
    if (hadRealtimeState) {
      logClientEvent({
        eventType: 'realtime.closed',
        provider: closingRealtimeProvider,
        severity: nextStatus === 'error' ? 'error' : 'info',
        payload: {
          nextStatus,
          committedAudio,
        },
      })
    }
    activeRealtimeProviderRef.current = null
  }, [fallbackRealtimeProvider, logClientEvent, resetInputLevel, stopOutputAudio])

  useEffect(() => {
    return () => closeRealtime('closed')
  }, [closeRealtime])

  const getOutputAudioContext = useCallback(() => {
    if (!outputAudioContextRef.current || outputAudioContextRef.current.state === 'closed') {
      outputAudioContextRef.current = createAudioContext()
    }
    return outputAudioContextRef.current
  }, [])

  const playPcmAudioOutput = useCallback(async (event: RealtimeAudioOutputEvent) => {
    const context = getOutputAudioContext()
    if (context.state === 'suspended') {
      await context.resume()
    }
    const audioBuffer = createPcm16AudioBuffer(context, event)
    if (audioBuffer.length === 0) return
    await new Promise<void>((resolve) => {
      const source = context.createBufferSource()
      outputAudioSourceRef.current = source
      source.buffer = audioBuffer
      source.connect(context.destination)
      source.onended = () => {
        if (outputAudioSourceRef.current === source) {
          outputAudioSourceRef.current = null
        }
        resolve()
      }
      source.start()
    })
  }, [getOutputAudioContext])

  const playBlobAudioOutput = useCallback(async (event: RealtimeAudioOutputEvent) => {
    const blob = new Blob([event.audio], { type: event.mimeType || 'audio/mpeg' })
    const objectUrl = URL.createObjectURL(blob)
    outputAudioUrlRef.current = objectUrl
    const audio = new Audio(objectUrl)
    outputAudioElementRef.current = audio

    try {
      await new Promise<void>((resolve, reject) => {
        let settled = false
        const resolveOnce = () => {
          if (settled) return
          settled = true
          resolve()
        }
        const rejectOnce = (error: Error) => {
          if (settled) return
          settled = true
          reject(error)
        }
        audio.onended = resolveOnce
        audio.onpause = resolveOnce
        audio.onerror = () => rejectOnce(new Error('Realtime audio output could not be played'))
        const playResult = audio.play()
        if (playResult) {
          void playResult.catch(rejectOnce)
        }
      })
    } finally {
      if (outputAudioElementRef.current === audio) {
        outputAudioElementRef.current = null
      }
      if (outputAudioUrlRef.current === objectUrl) {
        outputAudioUrlRef.current = null
      }
      audio.pause()
      URL.revokeObjectURL(objectUrl)
    }
  }, [])

  const playRealtimeAudioOutput = useCallback(async (event: RealtimeAudioOutputEvent) => {
    setError(null)
    setStatus('speaking')
    setPreview(tr('AI 正在说话', 'AI is speaking'))
    try {
      if (isPcmAudioOutput(event)) {
        await playPcmAudioOutput(event)
      } else {
        await playBlobAudioOutput(event)
      }
      logClientEvent({
        eventType: 'audio.output_played',
        payload: {
          mimeType: event.mimeType,
          sequence: event.sequence,
          contextId: event.contextId,
          sampleRate: event.sampleRate,
          channels: event.channels,
          audioBytes: event.audio.byteLength,
        },
      })
    } finally {
      setStatus((current) => (current === 'speaking' ? 'listening' : current))
    }
  }, [logClientEvent, playBlobAudioOutput, playPcmAudioOutput, tr])

  const handleAudioOutputPlaybackError = useCallback(() => {
    setError(tr('实时语音播放失败', 'Realtime audio playback failed'))
    setStatus('error')
    logClientEvent({
      eventType: 'audio.output_playback_failed',
      severity: 'error',
      message: 'Realtime audio playback failed',
    })
  }, [logClientEvent, tr])

  useEffect(() => {
    const queue = new RealtimeAudioOutputQueue({
      play: playRealtimeAudioOutput,
      onError: handleAudioOutputPlaybackError,
    })
    outputAudioQueueRef.current = queue
    return () => {
      queue.clear()
      if (outputAudioQueueRef.current === queue) {
        outputAudioQueueRef.current = null
      }
    }
  }, [handleAudioOutputPlaybackError, playRealtimeAudioOutput])

  const handleRealtimeEvent = useCallback((event: RealtimeServerEvent) => {
    if (event.type === 'audio.output') {
      logClientEvent({
        eventType: 'audio.output_received',
        payload: {
          mimeType: event.mimeType,
          sequence: event.sequence,
          contextId: event.contextId,
          sampleRate: event.sampleRate,
          channels: event.channels,
          audioBytes: event.audio.byteLength,
          status: event.status,
        },
      })
      outputAudioQueueRef.current?.enqueue(event)
      return
    }
    if (event.type === 'error') {
      const message = typeof event.message === 'string' && event.message.trim()
        ? event.message
        : tr('实时语音通道错误', 'Realtime voice error')
      logClientEvent({
        eventType: 'realtime.server_error',
        severity: 'error',
        errorCategory: event.errorCategory,
        message,
        payload: {
          code: event.code,
          phase: event.phase,
          provider: event.provider,
          realtimeRuntime: event.realtimeRuntime,
          sourceEventType: event.eventType,
          retryable: event.retryable,
          fatal: event.fatal,
        },
      })
      setError(message)
      setStatus('error')
      return
    }
    if (event.type === 'user_turn.started') {
      setStatus('listening')
      setPreview(tr('正在听你说话', 'Listening to you'))
      return
    }
    if (event.type === 'user_turn.stopped') {
      setStatus('processing')
      setPreview(tr('正在整理你的回答', 'Processing your turn'))
      return
    }
    if (event.type === 'assistant_speaking.started') {
      setStatus('speaking')
      setPreview(tr('AI 正在说话', 'AI is speaking'))
      return
    }
    if (event.type === 'assistant_speaking.stopped') {
      setStatus('listening')
      setPreview(tr('AI 已暂停', 'AI paused'))
      return
    }
    if (event.type === 'interrupted') {
      setStatus('listening')
      setPreview(tr('已打断 AI 输出', 'AI output interrupted'))
      return
    }
    if (event.type === 'silence_timeout') {
      setStatus('listening')
      setPreview(tr('等待下一句输入', 'Waiting for the next turn'))
      return
    }

    if (event.type === 'transcript.delta' && transcriptTextFromEvent(event)) {
      setPreview(tr('正在转写语音', 'Transcribing voice'))
      return
    }
    if (event.type === 'transcript.done') {
      const content = transcriptTextFromEvent(event)
      if (!content) return
      const role = transcriptRoleFromEvent(event)
      const key = realtimeEventKey(event, role, content, 'final')
      if (!transcriptKeysRef.current.has(key)) {
        transcriptKeysRef.current.add(key)
        setPreview(role === 'assistant'
          ? tr('AI 语音文本已生成', 'AI transcript ready')
          : tr('你的语音文本已生成', 'Your transcript is ready'))
        onFinalTranscript?.(content, role)
      }
      return
    }
    if (event.type === 'transcript.persisted') {
      const message = persistedTranscriptMessageFromEvent(event)
      const content = message ? textValue(message.content) : transcriptTextFromEvent(event)
      const role = message
        ? realtimeRoleFromPersistedMessage(message, transcriptRoleFromEvent(event))
        : transcriptRoleFromEvent(event)
      const chatMessage = message
        ? realtimeMessageToChatMessage({ ...message, content }, role, event.createdAt)
        : null
      const key = chatMessage ? `message:${chatMessage.id}` : realtimeEventKey(event, role, content, 'persisted')
      if (content && !transcriptKeysRef.current.has(key)) {
        transcriptKeysRef.current.add(key)
        setPreview(role === 'assistant'
          ? tr('AI 回复已保存', 'AI reply saved')
          : tr('你的语音文本已显示在对话中', 'Your transcript is shown in the chat'))
        onPersistedTranscript?.(content, role, chatMessage || undefined)
        logClientEvent({
          eventType: 'transcript.persisted',
          payload: {
            messageId: chatMessage?.id ?? message?.id,
            senderType: chatMessage?.sender_type ?? message?.sender_type,
            role,
            persistedRoomId: chatMessage?.room_id ?? message?.room_id,
          },
        })
      }
    }
  }, [logClientEvent, onFinalTranscript, onPersistedTranscript, tr])

  const startRealtime = useCallback(async () => {
    if (!roomId || !trainingSessionId || disabled) return
    if (
      realtimeSessionRef.current
      || localStreamRef.current
      || inputAudioContextRef.current
      || outputAudioContextRef.current
    ) {
      closeRealtime('closed')
    }
    transcriptKeysRef.current.clear()
    setError(null)
    setPreview(counterpartName ? tr('正在连接 {name}', 'Connecting to {name}', { name: counterpartName }) : '')
    setStatus('connecting')
    const configuredRealtimeProvider = await loadConfiguredRealtimeProvider()
    const realtimeRuntimeProvider = resolveTrainingRealtimeWebSocketProvider(configuredRealtimeProvider)
    activeRealtimeProviderRef.current = realtimeRuntimeProvider
    const audioContract = getRealtimeVoiceAudioContract(realtimeProfile)
    startFailureLoggedRef.current = false
    inputSendErrorLoggedRef.current = false
    logClientEvent({
      eventType: 'realtime.start_requested',
      provider: realtimeRuntimeProvider,
      configuredRealtimeProvider,
      payload: {
        realtimeProvider: realtimeRuntimeProvider,
        configuredRealtimeProvider: configuredRealtimeProvider || undefined,
        realtimeProfile: audioContract.realtimeProfile,
        latencyProfile: audioContract.latencyProfile,
        inputSampleRate: audioContract.inputSampleRate,
        outputSampleRate: audioContract.outputSampleRate,
        roomId,
        hasTranscriptMetadata: Boolean(transcriptMetadata),
      },
    })

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        startFailureLoggedRef.current = true
        logClientEvent({
          eventType: 'mic.unavailable',
          severity: 'error',
          message: 'getUserMedia unavailable',
          payload: {
            hasMediaDevices: Boolean(navigator.mediaDevices),
          },
        })
        throw new Error(tr('当前浏览器不可用麦克风录音', 'getUserMedia unavailable'))
      }

      const session = createRealtimeSession({
        url: getTrainingRealtimeWebSocketUrl({
          sessionId: trainingSessionId,
          roomId,
          provider: realtimeRuntimeProvider,
          audioFormat: 'pcm16',
          profile: realtimeProfile,
        }),
        onStatusChange: (nextStatus) => {
          if (realtimeSessionRef.current !== session) return
          setStatus(nextStatus)
          if (nextStatus === 'connected') {
            logClientEvent({
              eventType: 'realtime.ws_connected',
              provider: realtimeRuntimeProvider,
              configuredRealtimeProvider,
              payload: {
                status: nextStatus,
                roomId,
                realtimeProvider: realtimeRuntimeProvider,
                configuredRealtimeProvider: configuredRealtimeProvider || undefined,
              },
            })
            try {
              session.send({
                type: 'session.start',
                sessionId: trainingSessionId,
                metadata: {
                  ...(transcriptMetadata || {}),
                  personaId: personaId || undefined,
                  realtimeProvider: configuredRealtimeProvider || realtimeRuntimeProvider,
                  runtimeProvider: realtimeRuntimeProvider,
                  realtimeProfile: audioContract.realtimeProfile,
                  inputSampleRate: audioContract.inputSampleRate,
                  audioContract,
                },
              })
              session.send({
                type: 'session.configure',
                sessionId: trainingSessionId,
                roomId,
              })
            } catch (sendError) {
              logClientEvent({
                eventType: 'realtime.configure_failed',
                provider: realtimeRuntimeProvider,
                configuredRealtimeProvider,
                severity: 'error',
                message: errorMessage(sendError, 'Realtime voice initialization failed'),
                payload: {
                  phase: 'session.configure',
                  roomId,
                  sessionId: trainingSessionId,
                  realtimeProvider: realtimeRuntimeProvider,
                },
              })
              setError(sendError instanceof Error ? sendError.message : tr('实时语音初始化失败', 'Realtime voice initialization failed'))
              setStatus('error')
            }
          }
          if (nextStatus === 'connected' || nextStatus === 'listening') {
            setPreview(tr('实时语音教练已连接', 'Realtime voice agent connected'))
          }
        },
        onEvent: (event) => {
          if (realtimeSessionRef.current !== session) return
          handleRealtimeEvent(event)
        },
        onError: (socketError) => {
          if (realtimeSessionRef.current !== session) return
          logClientEvent({
            eventType: 'realtime.ws_error',
            provider: realtimeRuntimeProvider,
            configuredRealtimeProvider,
            severity: 'error',
            message: socketError.message || 'Realtime voice channel error',
            payload: {
              name: socketError.name,
              realtimeProvider: realtimeRuntimeProvider,
            },
          })
          setError(socketError.message || tr('实时语音通道错误', 'Realtime voice channel error'))
          setStatus('error')
        },
      })
      realtimeSessionRef.current = session

      const localStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      localStreamRef.current = localStream
      logClientEvent({
        eventType: 'mic.capture_started',
        provider: realtimeRuntimeProvider,
        configuredRealtimeProvider,
        payload: {
          trackCount: localStream.getAudioTracks().length,
          inputSampleRate: audioContract.inputSampleRate,
          outputSampleRate: audioContract.outputSampleRate,
          realtimeProfile: audioContract.realtimeProfile,
          realtimeProvider: realtimeRuntimeProvider,
        },
      })

      const audioContext = createAudioContext()
      inputAudioContextRef.current = audioContext
      if (audioContext.state === 'suspended') {
        await audioContext.resume()
      }
      const source = audioContext.createMediaStreamSource(localStream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      const silence = audioContext.createGain()
      silence.gain.value = 0
      source.connect(processor)
      processor.connect(silence)
      silence.connect(audioContext.destination)
      inputAudioSourceRef.current = source
      inputAudioProcessorRef.current = processor
      inputAudioSilenceRef.current = silence

      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0)
        emitInputLevel(inputLevelFromSamples(input))
        const activeSession = realtimeSessionRef.current
        if (activeSession !== session || !activeSession.isConnected) return
        const audio = encodePcm16Mono(input, audioContext.sampleRate, audioContract.inputSampleRate)
        try {
          activeSession.send({ type: 'audio.input', audio, mimeType: 'audio/pcm' })
        } catch (sendError) {
          if (!inputSendErrorLoggedRef.current) {
            inputSendErrorLoggedRef.current = true
            logClientEvent({
              eventType: 'audio.input_send_failed',
              provider: realtimeRuntimeProvider,
              configuredRealtimeProvider,
              severity: 'error',
              message: errorMessage(sendError, 'Failed to send realtime audio'),
              payload: {
                sampleRate: audioContext.sampleRate,
                outputSampleRate: audioContract.inputSampleRate,
                audioBytes: audio.byteLength,
                realtimeProvider: realtimeRuntimeProvider,
              },
            })
          }
          setError(sendError instanceof Error ? sendError.message : tr('发送实时音频失败', 'Failed to send realtime audio'))
          setStatus('error')
        }
      }

      session.connect()
    } catch (err) {
      if (!startFailureLoggedRef.current) {
        const failureMessage = errorMessage(err, 'Failed to start realtime voice agent')
        const failureEventType = isMicrophonePermissionError(err)
          ? 'mic.permission_denied'
          : failureMessage.includes('getUserMedia unavailable')
            ? 'mic.unavailable'
            : 'realtime.start_failed'
        startFailureLoggedRef.current = true
        logClientEvent({
          eventType: failureEventType,
          provider: realtimeRuntimeProvider,
          configuredRealtimeProvider,
          severity: 'error',
          message: failureMessage,
          payload: {
            errorName: errorName(err),
            roomId,
            trainingSessionId,
            realtimeProvider: realtimeRuntimeProvider,
            realtimeProfile: audioContract.realtimeProfile,
          },
        })
      }
      closeRealtime('error')
      setError(err instanceof Error ? err.message : tr('启动实时语音教练失败', 'Failed to start realtime voice agent'))
    }
  }, [closeRealtime, counterpartName, disabled, handleRealtimeEvent, loadConfiguredRealtimeProvider, logClientEvent, personaId, realtimeProfile, roomId, trainingSessionId, transcriptMetadata, tr])

  const active = status === 'connecting'
    || status === 'connected'
    || status === 'preparing'
    || status === 'listening'
    || status === 'processing'
    || status === 'speaking'
  const label = statusLabel(status, error, tr)
  const actionDisabled = status === 'connecting' || (!active && (disabled || !roomId || !trainingSessionId))
  const actionTitle = active ? tr('停止实时语音教练', 'Stop realtime voice agent') : tr('启动实时语音教练', 'Start realtime voice agent')

  return (
    <div className="realtime-voice-recorder">
      <div className="realtime-voice-status" aria-live="polite">
        <span>{label}</span>
        {preview && <small>{preview}</small>}
      </div>
      <Button
        variant="secondary"
        size="sm"
        className={`realtime-voice-action${active ? ' active' : ''}`}
        onClick={active ? () => closeRealtime('closed') : startRealtime}
        disabled={actionDisabled}
        title={actionTitle}
        aria-label={actionTitle}
      >
        {status === 'connecting'
          ? <Loader2 size={14} className="spin" />
          : active
            ? <Square size={14} />
            : <Mic size={14} />}
        <span className="realtime-voice-action-label">
        {active ? tr('停止', 'Stop') : tr('开始', 'Start')}
        </span>
      </Button>
    </div>
  )
}
