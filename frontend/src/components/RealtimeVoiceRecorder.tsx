import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Mic, Square } from 'lucide-react'
import {
  decodeRealtimeServerEvent,
  createTrainingRealtimeSdpAnswer,
  persistTrainingRealtimeTranscripts,
  RealtimeAudioOutputQueue,
  type RealtimeAudioOutputEvent,
  type RealtimeSessionStatus,
  type RealtimeTranscriptRole,
} from '../services/realtimeSession'
import { useI18n } from '../i18n'

type OpenAIRealtimeEvent = Record<string, unknown> & {
  type?: string
  event_id?: string
  item_id?: string
  response_id?: string
  transcript?: string
  text?: string
  response?: {
    id?: string
    output?: Array<Record<string, unknown>>
  }
}

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

function eventText(event: OpenAIRealtimeEvent): string {
  if (typeof event.transcript === 'string') return event.transcript.trim()
  if (typeof event.text === 'string') return event.text.trim()
  return ''
}

function responseDoneTranscript(event: OpenAIRealtimeEvent): string {
  const output = event.response?.output
  if (!Array.isArray(output)) return ''

  const parts: string[] = []
  for (const item of output) {
    const content = item.content
    if (!Array.isArray(content)) continue
    for (const part of content) {
      if (!part || typeof part !== 'object') continue
      const transcript = (part as { transcript?: unknown }).transcript
      const text = (part as { text?: unknown }).text
      if (typeof transcript === 'string' && transcript.trim()) {
        parts.push(transcript.trim())
      } else if (typeof text === 'string' && text.trim()) {
        parts.push(text.trim())
      }
    }
  }
  return parts.join(' ').trim()
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
  const peerRef = useRef<RTCPeerConnection | null>(null)
  const dataChannelRef = useRef<RTCDataChannel | null>(null)
  const localStreamRef = useRef<MediaStream | null>(null)
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null)
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
    dataChannelRef.current?.close()
    dataChannelRef.current = null
    peerRef.current?.close()
    peerRef.current = null
    localStreamRef.current?.getTracks().forEach((track) => track.stop())
    localStreamRef.current = null
    if (remoteAudioRef.current) {
      remoteAudioRef.current.pause()
      remoteAudioRef.current.srcObject = null
    }
    remoteAudioRef.current = null
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
    setPreview(tr('AI is speaking', 'AI is speaking'))
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
    setError(tr('Realtime audio playback failed', 'Realtime audio playback failed'))
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

  const persistTranscript = useCallback(async (
    role: RealtimeTranscriptRole,
    text: string,
    event: OpenAIRealtimeEvent,
  ) => {
    const content = text.trim()
    if (!content || !roomId || !trainingSessionId) return
    const key = `${role}:${content}`
    if (transcriptKeysRef.current.has(key)) return
    transcriptKeysRef.current.add(key)
    try {
      await persistTrainingRealtimeTranscripts({
        sessionId: trainingSessionId,
        roomId,
        messages: [{
          role,
          content,
          event_id: event.event_id,
          item_id: event.item_id,
          response_id: event.response_id || event.response?.id,
          sender_id: role === 'assistant' ? personaId || 'assistant' : undefined,
          metadata: {
            ...(transcriptMetadata || {}),
            eventType: event.type,
          },
        }],
      })
      setPreview(content)
      onPersistedTranscript?.(content, role)
    } catch (err) {
      setError(err instanceof Error ? err.message : tr('保存实时转写失败', 'Failed to save realtime transcript'))
    }
  }, [onPersistedTranscript, personaId, roomId, trainingSessionId, transcriptMetadata, tr])

  const handleRealtimeEvent = useCallback((raw: string) => {
    const decoded = decodeRealtimeServerEvent(raw)
    if (decoded?.type === 'audio.output') {
      outputAudioQueueRef.current?.enqueue(decoded)
      return
    }
    if (decoded?.type === 'error') {
      const message = typeof decoded.message === 'string' && decoded.message.trim()
        ? decoded.message
        : tr('OpenAI realtime error', 'OpenAI realtime error')
      setError(message)
      setStatus('error')
      return
    }

    let event: OpenAIRealtimeEvent
    try {
      event = JSON.parse(raw) as OpenAIRealtimeEvent
    } catch {
      return
    }

    if (event.type === 'error') {
      const message = typeof event.message === 'string' ? event.message : tr('OpenAI 实时通道错误', 'OpenAI realtime error')
      setError(message)
      setStatus('error')
      return
    }
    if (event.type === 'input_audio_buffer.speech_started') {
      setStatus('listening')
      setPreview(tr('正在聆听...', 'Listening...'))
    }
    if (event.type === 'response.created') {
      setStatus('speaking')
    }
    if (event.type === 'response.done') {
      setStatus('listening')
      const transcript = responseDoneTranscript(event)
      if (transcript) void persistTranscript('assistant', transcript, event)
    }

    if (
      event.type === 'conversation.item.input_audio_transcription.completed'
      || event.type === 'input_audio_transcription.completed'
    ) {
      const transcript = eventText(event)
      if (transcript) void persistTranscript('user', transcript, event)
    }

    if (
      event.type === 'response.audio_transcript.done'
      || event.type === 'response.output_audio_transcript.done'
    ) {
      const transcript = eventText(event)
      if (transcript) void persistTranscript('assistant', transcript, event)
    }
  }, [persistTranscript, tr])

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

      const peer = new RTCPeerConnection()
      peerRef.current = peer

      const remoteAudio = new Audio()
      remoteAudio.autoplay = true
      remoteAudioRef.current = remoteAudio
      peer.ontrack = (event) => {
        remoteAudio.srcObject = event.streams[0]
        void remoteAudio.play().catch(() => {})
      }

      const localStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      localStreamRef.current = localStream
      localStream.getAudioTracks().forEach((track) => peer.addTrack(track, localStream))

      const dataChannel = peer.createDataChannel('oai-events')
      dataChannelRef.current = dataChannel
      dataChannel.onopen = () => {
        setStatus('listening')
        setPreview(tr('实时语音教练已连接', 'Realtime voice agent connected'))
      }
      dataChannel.onmessage = (message) => {
        if (typeof message.data === 'string') {
          handleRealtimeEvent(message.data)
        }
      }
      dataChannel.onerror = () => {
        setError(tr('实时数据通道错误', 'Realtime data channel error'))
        setStatus('error')
      }

      const offer = await peer.createOffer()
      await peer.setLocalDescription(offer)
      const answerSdp = await createTrainingRealtimeSdpAnswer({
        offerSdp: offer.sdp || '',
        sessionId: trainingSessionId,
        roomId,
      })
      await peer.setRemoteDescription({ type: 'answer', sdp: answerSdp })
      setStatus('connected')
    } catch (err) {
      closeRealtime('error')
      setError(err instanceof Error ? err.message : tr('启动实时语音教练失败', 'Failed to start realtime voice agent'))
    }
  }, [closeRealtime, counterpartName, disabled, handleRealtimeEvent, roomId, trainingSessionId, tr])

  const active = status === 'connecting' || status === 'connected' || status === 'listening' || status === 'speaking'
  const label = statusLabel(status, error, tr)

  return (
    <div className="realtime-voice-recorder">
      <div className="realtime-voice-status">
        <span>{label}</span>
        {preview && <small>{preview}</small>}
      </div>
      <button
        className={`realtime-voice-action${active ? ' active' : ''}`}
        type="button"
        onClick={active ? () => closeRealtime('closed') : startRealtime}
        disabled={disabled || !roomId || !trainingSessionId || status === 'connecting'}
        title={active ? tr('停止实时语音教练', 'Stop realtime voice agent') : tr('启动实时语音教练', 'Start realtime voice agent')}
      >
        {status === 'connecting'
          ? <Loader2 size={14} className="spin" />
          : active
            ? <Square size={14} />
            : <Mic size={14} />}
        {active ? tr('停止', 'Stop') : tr('开始', 'Start')}
      </button>
    </div>
  )
}
