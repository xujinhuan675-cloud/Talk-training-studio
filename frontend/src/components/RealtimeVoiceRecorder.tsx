import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Mic, Square } from 'lucide-react'
import {
  createRealtimeSession,
  getTrainingRealtimeWebSocketUrl,
  RealtimeAudioOutputQueue,
  type RealtimeServerEvent,
  type RealtimeSession,
  type RealtimeAudioOutputEvent,
  type RealtimeSessionStatus,
  type RealtimeTranscriptRole,
} from '../services/realtimeSession'
import { useI18n } from '../i18n'
import { Button } from './ui/button'

export interface RealtimeVoiceRecorderProps {
  roomId: number | null
  trainingSessionId: string | null
  disabled?: boolean
  personaId?: string | null
  counterpartName?: string
  transcriptMetadata?: Record<string, unknown>
  onPersistedTranscript?: (text: string, role: RealtimeTranscriptRole) => void
}

function statusLabel(
  status: RealtimeSessionStatus,
  error: string | null,
  tr: (zhText: string, enText: string) => string,
): string {
  if (error) return error
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

function realtimeRoleFromSender(senderType: unknown): RealtimeTranscriptRole {
  const normalized = typeof senderType === 'string' ? senderType.trim().toLowerCase() : ''
  return normalized === 'persona' || normalized === 'assistant' ? 'assistant' : 'user'
}

export default function RealtimeVoiceRecorder({
  roomId,
  trainingSessionId,
  disabled,
  personaId,
  counterpartName,
  transcriptMetadata,
  onPersistedTranscript,
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
  const [status, setStatus] = useState<RealtimeSessionStatus>('idle')
  const [preview, setPreview] = useState('')
  const [error, setError] = useState<string | null>(null)

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
    stopOutputAudio()
    inputAudioProcessorRef.current?.disconnect()
    inputAudioProcessorRef.current = null
    inputAudioSourceRef.current?.disconnect()
    inputAudioSourceRef.current = null
    inputAudioSilenceRef.current?.disconnect()
    inputAudioSilenceRef.current = null
    const realtimeSession = realtimeSessionRef.current
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
  }, [stopOutputAudio])

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
    } finally {
      setStatus((current) => (current === 'speaking' ? 'listening' : current))
    }
  }, [playBlobAudioOutput, playPcmAudioOutput, tr])

  const handleAudioOutputPlaybackError = useCallback(() => {
    setError(tr('实时语音播放失败', 'Realtime audio playback failed'))
    setStatus('error')
  }, [tr])

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
      outputAudioQueueRef.current?.enqueue(event)
      return
    }
    if (event.type === 'error') {
      const message = typeof event.message === 'string' && event.message.trim()
        ? event.message
        : tr('Pipecat 实时通道错误', 'Pipecat realtime error')
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

    if (event.type === 'transcript.delta' && event.text.trim()) {
      setPreview(event.text.trim())
      return
    }
    if (event.type === 'transcript.done' && event.text.trim()) {
      setPreview(event.text.trim())
      return
    }
    if (event.type === 'transcript.persisted') {
      const message = event.payload.message
      const content = typeof message.content === 'string' ? message.content.trim() : ''
      const role = realtimeRoleFromSender(message.sender_type)
      const key = `${role}:${content}`
      if (content && !transcriptKeysRef.current.has(key)) {
        transcriptKeysRef.current.add(key)
        setPreview(content)
        onPersistedTranscript?.(content, role)
      }
    }
  }, [onPersistedTranscript, tr])

  const startRealtime = useCallback(async () => {
    if (!roomId || !trainingSessionId || disabled) return
    closeRealtime('closed')
    transcriptKeysRef.current.clear()
    setError(null)
    setPreview(counterpartName ? tr('正在连接 {name}', 'Connecting to {name}', { name: counterpartName }) : '')
    setStatus('connecting')

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(tr('当前浏览器不可用麦克风录音', 'getUserMedia unavailable'))
      }

      const session = createRealtimeSession({
        url: getTrainingRealtimeWebSocketUrl({
          sessionId: trainingSessionId,
          roomId,
          audioFormat: 'pcm16',
        }),
        onStatusChange: (nextStatus) => {
          setStatus(nextStatus)
          if (nextStatus === 'connected') {
            try {
              session.send({
                type: 'session.start',
                sessionId: trainingSessionId,
                metadata: {
                  ...(transcriptMetadata || {}),
                  personaId: personaId || undefined,
                },
              })
              session.send({
                type: 'session.configure',
                sessionId: trainingSessionId,
                roomId,
              })
            } catch (sendError) {
              setError(sendError instanceof Error ? sendError.message : tr('实时语音初始化失败', 'Realtime voice initialization failed'))
              setStatus('error')
            }
          }
          if (nextStatus === 'connected' || nextStatus === 'listening') {
            setPreview(tr('实时语音教练已连接', 'Realtime voice agent connected'))
          }
        },
        onEvent: handleRealtimeEvent,
        onError: (socketError) => {
          setError(socketError.message || tr('Pipecat 实时通道错误', 'Pipecat realtime channel error'))
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
        const activeSession = realtimeSessionRef.current
        if (activeSession !== session || !activeSession.isConnected) return
        const input = event.inputBuffer.getChannelData(0)
        const audio = encodePcm16Mono(input, audioContext.sampleRate)
        try {
          activeSession.send({ type: 'audio.input', audio, mimeType: 'audio/pcm' })
        } catch (sendError) {
          setError(sendError instanceof Error ? sendError.message : tr('发送实时音频失败', 'Failed to send realtime audio'))
          setStatus('error')
        }
      }

      session.connect()
    } catch (err) {
      closeRealtime('error')
      setError(err instanceof Error ? err.message : tr('启动实时语音教练失败', 'Failed to start realtime voice agent'))
    }
  }, [closeRealtime, counterpartName, disabled, handleRealtimeEvent, personaId, roomId, trainingSessionId, transcriptMetadata, tr])

  const active = status === 'connecting' || status === 'connected' || status === 'listening' || status === 'speaking'
  const label = statusLabel(status, error, tr)
  const actionTitle = active ? tr('停止实时语音教练', 'Stop realtime voice agent') : tr('启动实时语音教练', 'Start realtime voice agent')

  return (
    <div className="realtime-voice-recorder">
      <div className="realtime-voice-status">
        <span>{label}</span>
        {preview && <small>{preview}</small>}
      </div>
      <Button
        variant="secondary"
        size="sm"
        className={`realtime-voice-action${active ? ' active' : ''}`}
        onClick={active ? () => closeRealtime('closed') : startRealtime}
        disabled={disabled || !roomId || !trainingSessionId || status === 'connecting'}
        title={actionTitle}
        aria-label={actionTitle}
      >
        {status === 'connecting'
          ? <Loader2 size={14} className="spin" />
          : active
            ? <Square size={14} />
            : <Mic size={14} />}
        {active ? tr('停止', 'Stop') : tr('开始', 'Start')}
      </Button>
    </div>
  )
}
