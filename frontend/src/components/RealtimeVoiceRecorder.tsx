import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Mic, Square } from 'lucide-react'
import {
  createTrainingRealtimeSdpAnswer,
  persistTrainingRealtimeTranscripts,
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
  onPersistedTranscript?: (text: string, role: RealtimeTranscriptRole) => void
}

function statusLabel(
  status: RealtimeSessionStatus,
  error: string | null,
  tr: (zhText: string, enText: string) => string,
): string {
  if (error) return error
  if (status === 'connecting' || status === 'preparing') return tr('Connecting realtime voice agent', 'Connecting realtime voice agent')
  if (status === 'speaking') return tr('AI is speaking', 'AI is speaking')
  if (status === 'listening' || status === 'connected') return tr('Realtime voice agent connected', 'Realtime voice agent connected')
  if (status === 'error') return tr('Realtime voice agent error', 'Realtime voice agent error')
  if (status === 'closed') return tr('Realtime voice agent stopped', 'Realtime voice agent stopped')
  return tr('Realtime voice agent ready', 'Realtime voice agent ready')
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

export default function RealtimeVoiceRecorder({
  roomId,
  trainingSessionId,
  disabled,
  personaId,
  counterpartName,
  onPersistedTranscript,
}: RealtimeVoiceRecorderProps) {
  const { tr } = useI18n()
  const peerRef = useRef<RTCPeerConnection | null>(null)
  const dataChannelRef = useRef<RTCDataChannel | null>(null)
  const localStreamRef = useRef<MediaStream | null>(null)
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null)
  const transcriptKeysRef = useRef<Set<string>>(new Set())
  const [status, setStatus] = useState<RealtimeSessionStatus>('idle')
  const [preview, setPreview] = useState('')
  const [error, setError] = useState<string | null>(null)

  const closeRealtime = useCallback((nextStatus: RealtimeSessionStatus = 'closed') => {
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
    setStatus(nextStatus)
  }, [])

  useEffect(() => {
    return () => closeRealtime('closed')
  }, [closeRealtime])

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
            eventType: event.type,
          },
        }],
      })
      setPreview(content)
      onPersistedTranscript?.(content, role)
    } catch (err) {
      setError(err instanceof Error ? err.message : tr('Failed to save realtime transcript', 'Failed to save realtime transcript'))
    }
  }, [onPersistedTranscript, personaId, roomId, trainingSessionId, tr])

  const handleRealtimeEvent = useCallback((raw: string) => {
    let event: OpenAIRealtimeEvent
    try {
      event = JSON.parse(raw) as OpenAIRealtimeEvent
    } catch {
      return
    }

    if (event.type === 'error') {
      const message = typeof event.message === 'string' ? event.message : tr('OpenAI realtime error', 'OpenAI realtime error')
      setError(message)
      setStatus('error')
      return
    }
    if (event.type === 'input_audio_buffer.speech_started') {
      setStatus('listening')
      setPreview(tr('Listening...', 'Listening...'))
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
    setPreview(counterpartName ? tr('Connecting to {name}', 'Connecting to {name}', { name: counterpartName }) : '')
    setStatus('connecting')

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('getUserMedia unavailable')
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
        setPreview(tr('Realtime voice agent connected', 'Realtime voice agent connected'))
      }
      dataChannel.onmessage = (message) => {
        if (typeof message.data === 'string') {
          handleRealtimeEvent(message.data)
        }
      }
      dataChannel.onerror = () => {
        setError(tr('Realtime data channel error', 'Realtime data channel error'))
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
      setError(err instanceof Error ? err.message : tr('Failed to start realtime voice agent', 'Failed to start realtime voice agent'))
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
        title={active ? tr('Stop realtime voice agent', 'Stop realtime voice agent') : tr('Start realtime voice agent', 'Start realtime voice agent')}
      >
        {status === 'connecting'
          ? <Loader2 size={14} className="spin" />
          : active
            ? <Square size={14} />
            : <Mic size={14} />}
        {active ? tr('Stop', 'Stop') : tr('Start', 'Start')}
      </button>
    </div>
  )
}
