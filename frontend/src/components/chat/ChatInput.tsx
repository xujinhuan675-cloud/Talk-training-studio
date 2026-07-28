import React from 'react'
import { Send, Lightbulb, Video } from 'lucide-react'
import Avatar from '../Avatar'
import VoiceRecorder, { type VoiceRecorderState } from '../VoiceRecorder'
import { Button } from '../ui/button'
import { Textarea } from '../ui/form'
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
  trainingSessionId?: string | null
  messageMetadata?: Record<string, unknown>
  onVoiceTranscription?: (text: string) => void
  onVoiceRecorderStateChange?: (state: VoiceRecorderState, error: string | null) => void
  showVoiceButton?: boolean
  realtimeVoiceControl?: React.ReactNode
  onVideoClick?: () => void
  videoActive?: boolean
  showVideoButton?: boolean
  onLiveCoachClick?: () => void
  showLiveCoachButton?: boolean
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
  trainingSessionId,
  messageMetadata,
  onVoiceTranscription,
  onVoiceRecorderStateChange,
  showVoiceButton = true,
  realtimeVoiceControl,
  onVideoClick,
  videoActive,
  showVideoButton = true,
  onLiveCoachClick,
  showLiveCoachButton = true,
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
      {realtimeVoiceControl && (
        <div className="message-input-realtime-slot">
          {realtimeVoiceControl}
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
                <Avatar name={p.name} color={p.avatar_color || '#0F766E'} size={24} />
                <span className="mention-name">{p.name}</span>
                <span className="mention-role">{p.role}</span>
              </div>
            ))}
          </div>
        )}
        <Textarea
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
        {roomId && showVoiceButton && (
          <VoiceRecorder
            roomId={roomId}
            trainingSessionId={trainingSessionId}
            disabled={sending}
            metadata={messageMetadata}
            onTranscription={onVoiceTranscription}
            onStateChange={onVoiceRecorderStateChange}
          />
        )}
        {showVideoButton && (
          <Button
            aria-label={tr('录制视频回答', 'Record video answer')}
            aria-pressed={videoActive}
            className={`video-toggle-btn${videoActive ? ' active' : ''}`}
            onClick={onVideoClick}
            size="icon"
            title={tr('录制视频回答', 'Record video answer')}
            variant="secondary"
            disabled={sending}
          >
            <Video size={18} />
          </Button>
        )}
        {showLiveCoachButton && (
          <Button
            aria-label={tr('询问教练', 'Ask coach')}
            className="live-coach-btn"
            onClick={onLiveCoachClick}
            size="icon"
            title={tr('询问教练', 'Ask coach')}
            disabled={coachingSending}
            variant="secondary"
          >
            <Lightbulb size={18} />
          </Button>
        )}
        <Button
          aria-label={tr('发送消息', 'Send message')}
          className="send-btn"
          onClick={onSend}
          disabled={!value.trim() || sending}
          size="icon"
          variant="primary"
        >
          <Send size={18} />
        </Button>
      </div>
    </div>
  )
}
