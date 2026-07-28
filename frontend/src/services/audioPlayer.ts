/**
 * AudioPlayQueue — plays audio chunks sequentially.
 *
 * Receives base64-encoded mp3 chunks from SSE audio_chunk events,
 * decodes them, and plays one after another using Web Audio API.
 * Deduplicates by (reply_id, sentence_index) to prevent double playback.
 */

type QueueItem = {
  personaId: string
  data: ArrayBuffer
  replyId?: string
  sentenceIndex?: number
}

export type AudioPlaybackErrorReason =
  | 'audio_context_unavailable'
  | 'audio_context_resume_failed'
  | 'audio_decode_failed'

export type AudioPlaybackErrorHandler = (
  error: unknown,
  detail: {
    reason: AudioPlaybackErrorReason
    personaId?: string | null
    replyId?: string
    sentenceIndex?: number
  },
) => void

export class AudioPlayQueue {
  private queue: QueueItem[] = []
  private playing = false
  private muted = false
  private audioContext: AudioContext | null = null
  private currentSource: AudioBufferSourceNode | null = null
  private onPlayingChange?: (playing: boolean, personaId: string | null) => void
  private onError?: AudioPlaybackErrorHandler
  /** Track seen (reply_id:sentence_index) keys to prevent duplicate playback. */
  private seenChunks = new Set<string>()

  constructor(opts?: {
    onPlayingChange?: (playing: boolean, personaId: string | null) => void
    onError?: AudioPlaybackErrorHandler
  }) {
    this.onPlayingChange = opts?.onPlayingChange
    this.onError = opts?.onError
  }

  private getContext(): AudioContext {
    if (!this.audioContext || this.audioContext.state === 'closed') {
      const AudioContextCtor = window.AudioContext
        || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AudioContextCtor) {
        throw new Error('Web Audio API is not available in this browser')
      }
      this.audioContext = new AudioContextCtor()
    }
    return this.audioContext
  }

  async unlock(): Promise<void> {
    if (this.muted) return
    try {
      const ctx = this.getContext()
      if (ctx.state === 'suspended') {
        await ctx.resume()
      }
    } catch (error) {
      this.onError?.(error, { reason: 'audio_context_resume_failed', personaId: null })
      throw error
    }
  }

  setMuted(muted: boolean): void {
    this.muted = muted
    if (muted) {
      this.stop()
    }
  }

  isMuted(): boolean {
    return this.muted
  }

  enqueue(personaId: string, base64Data: string, replyId?: string, sentenceIndex?: number): boolean {
    if (this.muted || !base64Data) return false

    // Deduplicate: skip if we've already enqueued this exact chunk
    if (replyId) {
      const key = `${replyId}:${sentenceIndex ?? 0}`
      if (this.seenChunks.has(key)) return false
      this.seenChunks.add(key)
    }

    try {
      const binary = atob(base64Data)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i)
      }
      this.queue.push({ personaId, data: bytes.buffer, replyId, sentenceIndex })
      if (!this.playing) {
        this.playNext()
      }
      return true
    } catch {
      this.onError?.(new Error('Invalid base64 audio payload'), {
        reason: 'audio_decode_failed',
        personaId,
        replyId,
        sentenceIndex,
      })
      return false
    }
  }

  stop(): void {
    this.queue = []
    this.seenChunks.clear()
    if (this.currentSource) {
      try {
        this.currentSource.stop()
      } catch {
        // Already stopped
      }
      this.currentSource = null
    }
    this.playing = false
    this.onPlayingChange?.(false, null)
  }

  private async playNext(): Promise<void> {
    if (this.queue.length === 0) {
      this.playing = false
      this.onPlayingChange?.(false, null)
      return
    }

    this.playing = true
    const item = this.queue.shift()!
    this.onPlayingChange?.(true, item.personaId)

    try {
      const ctx = this.getContext()
      if (ctx.state === 'suspended') {
        try {
          await ctx.resume()
        } catch (error) {
          this.onError?.(error, {
            reason: 'audio_context_resume_failed',
            personaId: item.personaId,
            replyId: item.replyId,
            sentenceIndex: item.sentenceIndex,
          })
          this.currentSource = null
          this.playNext()
          return
        }
      }
      const audioBuffer = await ctx.decodeAudioData(item.data.slice(0))
      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)
      this.currentSource = source

      await new Promise<void>((resolve) => {
        source.onended = () => {
          this.currentSource = null
          resolve()
        }
        source.start(0)
      })
    } catch (error) {
      this.onError?.(error, {
        reason: this.audioContext ? 'audio_decode_failed' : 'audio_context_unavailable',
        personaId: item.personaId,
        replyId: item.replyId,
        sentenceIndex: item.sentenceIndex,
      })
      this.currentSource = null
    }

    this.playNext()
  }

  destroy(): void {
    this.stop()
    if (this.audioContext) {
      this.audioContext.close().catch(() => {})
      this.audioContext = null
    }
  }
}
