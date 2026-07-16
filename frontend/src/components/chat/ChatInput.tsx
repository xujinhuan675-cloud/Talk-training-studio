import React from 'react'
import { Send, Lightbulb, Video } from 'lucide-react'
import Avatar from '../Avatar'
import VoiceRecorder, { type VoiceRecorderState } from '../VoiceRecorder'
import type { PersonaSummary } from '../../services/api'
import { useI18n } from '../../i18n'
import './ChatInput.css'

export interface ChatInputProps {
  value: string
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  onSend: () => void
  sending: boolean
  placeholder?: string
  mentionQuery: string | null
  mentionResults: PersonaSummary[]
  onInsertMention: (persona: PersonaSummary) => void
  roomId: number | null
  onVoiceTranscription?: (text: string) => void
  onVoiceRecorderStateChange?: (state: VoiceRecorderState, error: string | null) => void
  onVideoClick?: () => void
  videoActive?: boolean
  onLiveCoachClick: () => void
  coachingSending: boolean
  sendError?: string | null
}

export default function ChatInput({
  value,
  onInputChange,
  onKeyDown,
  onSend,
  sending,
  placeholder,
  mentionQuery,
  mentionResults,
  onInsertMention,
  roomId,
  onVoiceTranscription,
  onVoiceRecorderStateChange,
  onVideoClick,
  videoActive,
  onLiveCoachClick,
  coachingSending,
  sendError,
}: ChatInputProps) {
  const { tr } = useI18n()
  const inputPlaceholder = placeholder ?? tr('输入消息...', 'Type a message...')

  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null)

  const resizeTextarea = React.useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 112)}px`
  }, [])

  React.useEffect(() => {
    resizeTextarea()
  }, [resizeTextarea, value])

  return (
    <div className="message-input-shell">
      {sendError && (
        <div className="message-input-error" role="alert">
          {sendError}
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
        <textarea
          ref={textareaRef}
          className="message-input-textarea"
          value={value}
          onChange={(e) => {
            onInputChange(e)
            resizeTextarea()
          }}
          onKeyDown={onKeyDown}
          placeholder={inputPlaceholder}
          disabled={sending}
          rows={1}
        />
        {roomId && (
          <VoiceRecorder
            roomId={roomId}
            disabled={sending}
            onTranscription={onVoiceTranscription}
            onStateChange={onVoiceRecorderStateChange}
          />
        )}
        <button
          className={`video-toggle-btn ${videoActive ? 'active' : ''}`}
          onClick={onVideoClick}
          title={tr('录制视频回答', 'Record video answer')}
          type="button"
          disabled={sending}
        >
          <Video size={18} />
        </button>
        <button
          className="live-coach-btn"
          onClick={onLiveCoachClick}
          title={tr('询问教练', 'Ask coach')}
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
