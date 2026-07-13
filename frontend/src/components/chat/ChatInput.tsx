import React from 'react'
import { Send, Lightbulb, Volume2, VolumeX, Video, X } from 'lucide-react'
import Avatar from '../Avatar'
import VoiceRecorder from '../VoiceRecorder'
import VideoAnswerRecorder, { type VideoAnswerResult } from '../VideoAnswerRecorder'
import type { PersonaSummary } from '../../services/api'
import './ChatInput.css'

export interface ChatInputProps {
  value: string
  onInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  onKeyDown: (e: React.KeyboardEvent) => void
  onSend: () => void
  sending: boolean
  placeholder?: string
  mentionQuery: string | null
  mentionResults: PersonaSummary[]
  onInsertMention: (persona: PersonaSummary) => void
  voiceEnabled: boolean
  voiceMuted: boolean
  onToggleVoice: () => void
  roomId: number | null
  onVoiceTranscription?: (text: string) => void
  onVideoRecorded?: (result: VideoAnswerResult) => void
  onLiveCoachClick: () => void
  coachingSending: boolean
}

export default function ChatInput({
  value,
  onInputChange,
  onKeyDown,
  onSend,
  sending,
  placeholder = 'Type a message...',
  mentionQuery,
  mentionResults,
  onInsertMention,
  voiceEnabled,
  voiceMuted,
  onToggleVoice,
  roomId,
  onVoiceTranscription,
  onVideoRecorded,
  onLiveCoachClick,
  coachingSending,
}: ChatInputProps) {
  const [videoOpen, setVideoOpen] = React.useState(false)

  return (
    <div className="message-input-shell">
      {videoOpen && (
        <div className="message-video-recorder-panel">
          <div className="message-video-recorder-header">
            <span>Video answer</span>
            <button type="button" onClick={() => setVideoOpen(false)} title="Close video recorder">
              <X size={16} />
            </button>
          </div>
          <VideoAnswerRecorder
            disabled={sending}
            onCancel={() => setVideoOpen(false)}
            onRecorded={(result) => {
              onVideoRecorded?.(result)
              setVideoOpen(false)
            }}
          />
        </div>
      )}

      <div className="message-input-bar">
        {mentionQuery !== null && mentionResults.length > 0 && (
          <div className="mention-dropdown">
            {mentionResults.map((p) => (
              <div
                key={p.id}
                className="mention-item"
                onClick={() => onInsertMention(p)}
              >
                <Avatar name={p.name} color={p.avatar_color || '#2D9C6F'} size={24} />
                <span className="mention-name">{p.name}</span>
                <span className="mention-role">{p.role}</span>
              </div>
            ))}
          </div>
        )}
        <input
          type="text"
          value={value}
          onChange={onInputChange}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={sending}
        />
        {voiceEnabled && roomId && (
          <VoiceRecorder
            roomId={roomId}
            disabled={sending}
            onTranscription={onVoiceTranscription}
          />
        )}
        <button
          className="video-toggle-btn"
          onClick={() => setVideoOpen((open) => !open)}
          title="Record video answer"
          type="button"
          disabled={sending}
        >
          <Video size={18} />
        </button>
        <button
          className={`voice-toggle-btn ${voiceMuted ? 'muted' : ''}`}
          onClick={onToggleVoice}
          title={!voiceEnabled ? 'Enable voice' : voiceMuted ? 'Disable voice mode' : 'Mute voice'}
          type="button"
        >
          {voiceEnabled && !voiceMuted ? <Volume2 size={18} /> : <VolumeX size={18} />}
        </button>
        <button
          className="live-coach-btn"
          onClick={onLiveCoachClick}
          title="Ask coach"
          disabled={coachingSending}
          type="button"
        >
          <Lightbulb size={18} />
        </button>
        <button className="send-btn" onClick={onSend} disabled={!value.trim() || sending} type="button">
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}
