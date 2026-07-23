import { useEffect, useRef, useState, useCallback } from 'react'
import { AudioPlayQueue } from '../services/audioPlayer'

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
}

export function useVoice(): UseVoiceReturn {
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
    })
    player.setMuted(true)
    audioPlayerRef.current = player
    return () => {
      player.destroy()
      audioPlayerRef.current = null
    }
  }, [])

  const toggleVoice = useCallback(() => {
    if (!voiceEnabled) {
      setVoiceEnabled(true)
      setVoiceMuted(false)
      setVoiceStatus('preparing')
      audioPlayerRef.current?.setMuted(false)
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
  }
}
