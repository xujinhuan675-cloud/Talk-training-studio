import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Camera, Circle, Play, Square, Trash2 } from 'lucide-react'
import './VideoAnswerRecorder.css'

export type VideoRecorderStatus = 'idle' | 'requesting' | 'ready' | 'recording' | 'recorded' | 'error'

export interface VideoAnswerResult {
  blob: Blob
  url: string
  mimeType: string
  durationMs: number
  size: number
  recordedAt: string
}

export interface VideoAnswerRecorderProps {
  onRecorded: (result: VideoAnswerResult) => void
  onCancel?: () => void
  maxDurationMs?: number
  disabled?: boolean
}

const MIME_CANDIDATES = [
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=vp8,opus',
  'video/webm',
  'video/mp4',
]

function pickSupportedMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type))
}

function formatDuration(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
}

export default function VideoAnswerRecorder({
  onRecorded,
  onCancel,
  maxDurationMs,
  disabled = false,
}: VideoAnswerRecorderProps) {
  const [status, setStatus] = useState<VideoRecorderStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [elapsedMs, setElapsedMs] = useState(0)
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const startedAtRef = useRef<number>(0)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const previewUrlRef = useRef<string | null>(null)

  const mimeType = useMemo(() => pickSupportedMimeType(), [])
  const canRecord = !disabled && status !== 'requesting' && status !== 'recording'

  const clearPreview = useCallback(() => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current)
      previewUrlRef.current = null
    }
    setPreviewUrl(null)
  }, [])

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }, [])

  const prepare = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus('error')
      setError('This browser does not support camera recording.')
      return null
    }

    setStatus('requesting')
    setError(null)
    clearPreview()

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: { facingMode: 'user' },
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        videoRef.current.muted = true
        await videoRef.current.play().catch(() => undefined)
      }
      setStatus('ready')
      return stream
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'Unable to access camera or microphone.')
      return null
    }
  }, [clearPreview])

  const startRecording = useCallback(async () => {
    if (disabled) return
    const stream = streamRef.current || await prepare()
    if (!stream) return

    try {
      chunksRef.current = []
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorderRef.current = recorder
      startedAtRef.current = Date.now()

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }

      recorder.onstop = () => {
        const finalMimeType = recorder.mimeType || mimeType || 'video/webm'
        const durationMs = Date.now() - startedAtRef.current
        const blob = new Blob(chunksRef.current, { type: finalMimeType })
        const url = URL.createObjectURL(blob)
        if (videoRef.current) {
          videoRef.current.srcObject = null
        }
        clearPreview()
        previewUrlRef.current = url
        setPreviewUrl(url)
        setElapsedMs(durationMs)
        setStatus('recorded')
        stopStream()
        onRecorded({
          blob,
          url,
          mimeType: finalMimeType,
          durationMs,
          size: blob.size,
          recordedAt: new Date().toISOString(),
        })
      }

      recorder.start(250)
      setElapsedMs(0)
      setStatus('recording')
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'Failed to start recording.')
      stopStream()
    }
  }, [clearPreview, disabled, mimeType, onRecorded, prepare, stopStream])

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
  }, [])

  const reset = useCallback(() => {
    stopRecording()
    stopStream()
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    clearPreview()
    setElapsedMs(0)
    setError(null)
    setStatus('idle')
    onCancel?.()
  }, [clearPreview, onCancel, stopRecording, stopStream])

  useEffect(() => {
    if (status !== 'recording') return undefined

    const timer = window.setInterval(() => {
      const nextElapsed = Date.now() - startedAtRef.current
      setElapsedMs(nextElapsed)
      if (maxDurationMs && nextElapsed >= maxDurationMs) {
        stopRecording()
      }
    }, 250)

    return () => window.clearInterval(timer)
  }, [maxDurationMs, status, stopRecording])

  useEffect(() => () => {
    stopRecording()
    stopStream()
    clearPreview()
  }, [clearPreview, stopRecording, stopStream])

  return (
    <div className="video-answer-recorder" data-status={status}>
      <div className="video-answer-preview">
        {previewUrl ? (
          <video ref={videoRef} src={previewUrl} controls playsInline />
        ) : (
          <video ref={videoRef} autoPlay muted playsInline />
        )}
        {status === 'idle' && (
          <div className="video-answer-empty">
            <Camera size={28} />
          </div>
        )}
      </div>

      <div className="video-answer-toolbar">
        <span className="video-answer-status">
          {status === 'recording' && <Circle size={10} fill="currentColor" />}
          {status === 'requesting' ? 'Requesting access' : formatDuration(elapsedMs)}
        </span>
        {status === 'recording' ? (
          <button type="button" onClick={stopRecording} disabled={disabled} title="Stop recording">
            <Square size={16} />
          </button>
        ) : (
          <button type="button" onClick={startRecording} disabled={!canRecord} title="Start recording">
            <Play size={16} />
          </button>
        )}
        <button type="button" onClick={reset} disabled={status === 'requesting'} title="Clear recording">
          <Trash2 size={16} />
        </button>
      </div>

      {error && <div className="video-answer-error">{error}</div>}
    </div>
  )
}
