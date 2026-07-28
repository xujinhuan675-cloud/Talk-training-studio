import { useEffect, useRef, useState, useCallback } from 'react'
import { AudioPlayQueue, type AudioPlaybackErrorReason } from '../services/audioPlayer'
import { useI18n } from '../i18n'

export type VoiceSessionStatus = 'idle' | 'preparing' | 'listening' | 'processing' | 'speaking' | 'error'

export interface UseVoiceReturn {
  voiceEnabled: boolean
  voiceMuted: boolean
  voiceStatus: VoiceSessionStatus
  voiceError: string | null
  playingPersonaId: string | null
  audioPlayerRef: React.RefObject<AudioPlayQueue | null>
  toggleVoice: () => void
  setVoiceStatus: (status: VoiceSessionStatus, error?: string | null) => void
  prepareVoiceSession: () => void
  startListening: () => void
  startProcessing: () => void
  startSpeaking: (personaId?: string | null) => void
  stopVoiceSession: () => void
  failVoiceSession: (error: string) => void
  markAudioOutputReceived: () => void
  markAudioOutputMissing: () => void
}

export function useVoice(): UseVoiceReturn {
  const { tr } = useI18n()
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [voiceMuted, setVoiceMuted] = useState(true)
  const [voiceStatus, setVoiceStatusState] = useState<VoiceSessionStatus>('idle')
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [playingPersonaId, setPlayingPersonaId] = useState<string | null>(null)
  const audioPlayerRef = useRef<AudioPlayQueue | null>(null)

  const setVoiceStatus = useCallback((status: VoiceSessionStatus, error: string | null = null) => {
    setVoiceStatusState(status)
    setVoiceError(error)
  }, [])

  const playbackErrorMessage = useCallback((reason: AudioPlaybackErrorReason): string => {
    if (reason === 'audio_context_unavailable') {
      return tr('当前浏览器不支持语音播放。', 'This browser does not support voice playback.')
    }
    if (reason === 'audio_context_resume_failed') {
      return tr('浏览器阻止了语音播放，请点击“开启语音”后重试。', 'The browser blocked voice playback. Click Enable voice and try again.')
    }
    return tr('AI 语音音频无法解码或播放，请检查 TTS 输出格式。', 'AI voice audio could not be decoded or played. Check the TTS output format.')
  }, [tr])

  // Initialize audio player
  useEffect(() => {
    const player = new AudioPlayQueue({
      onPlayingChange: (_playing, personaId) => {
        setPlayingPersonaId(personaId)
        setVoiceStatusState((current) => {
          if (personaId) return 'speaking'
          return current === 'speaking' ? 'idle' : current
        })
      },
      onError: (_error, detail) => {
        setPlayingPersonaId(null)
        setVoiceStatus('error', playbackErrorMessage(detail.reason))
      },
    })
    player.setMuted(true)
    audioPlayerRef.current = player
    return () => {
      player.destroy()
      audioPlayerRef.current = null
    }
  }, [playbackErrorMessage, setVoiceStatus])

  const toggleVoice = useCallback(() => {
    if (!voiceEnabled) {
      setVoiceEnabled(true)
      setVoiceMuted(false)
      setVoiceStatus('preparing')
      audioPlayerRef.current?.setMuted(false)
      audioPlayerRef.current?.unlock().catch(() => undefined)
    } else if (!voiceMuted) {
      setVoiceMuted(true)
      setVoiceStatus('idle')
      audioPlayerRef.current?.setMuted(true)
    } else {
      setVoiceEnabled(false)
      setVoiceMuted(false)
      setVoiceStatus('idle')
      audioPlayerRef.current?.setMuted(true)
    }
  }, [setVoiceStatus, voiceEnabled, voiceMuted])

  const prepareVoiceSession = useCallback(() => {
    setVoiceEnabled(true)
    setVoiceMuted(false)
    audioPlayerRef.current?.setMuted(false)
    setVoiceStatus('preparing')
    audioPlayerRef.current?.unlock().catch(() => undefined)
  }, [setVoiceStatus])

  const startListening = useCallback(() => {
    setVoiceStatus('listening')
  }, [setVoiceStatus])

  const startProcessing = useCallback(() => {
    setVoiceStatus('processing')
  }, [setVoiceStatus])

  const startSpeaking = useCallback((personaId: string | null = null) => {
    setPlayingPersonaId(personaId)
    setVoiceStatus('speaking')
  }, [setVoiceStatus])

  const stopVoiceSession = useCallback(() => {
    audioPlayerRef.current?.stop()
    audioPlayerRef.current?.setMuted(true)
    setVoiceEnabled(false)
    setVoiceMuted(true)
    setPlayingPersonaId(null)
    setVoiceStatus('idle')
  }, [setVoiceStatus])

  const failVoiceSession = useCallback((error: string) => {
    setPlayingPersonaId(null)
    setVoiceStatus('error', error)
  }, [setVoiceStatus])

  const markAudioOutputReceived = useCallback(() => {
    setVoiceError(null)
  }, [])

  const markAudioOutputMissing = useCallback(() => {
    setPlayingPersonaId(null)
    setVoiceStatus('error', tr(
      'AI 文字回复已生成，但本轮没有收到 TTS 音频。请检查设置里的 TTS 运行时状态和后端日志。',
      'AI text reply was generated, but no TTS audio was received for this turn. Check the TTS runtime status in Settings and the backend logs.',
    ))
  }, [setVoiceStatus, tr])

  return {
    voiceEnabled,
    voiceMuted,
    voiceStatus,
    voiceError,
    playingPersonaId,
    audioPlayerRef,
    toggleVoice,
    setVoiceStatus,
    prepareVoiceSession,
    startListening,
    startProcessing,
    startSpeaking,
    stopVoiceSession,
    failVoiceSession,
    markAudioOutputReceived,
    markAudioOutputMissing,
  }
}
