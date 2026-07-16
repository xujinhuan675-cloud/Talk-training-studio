import { useEffect, useRef, useState, useCallback } from 'react'
import {
  fetchRoomDetail,
  sendMessage as apiSendMessage,
  type ChatRoomDetail,
  type DispatchPhase,
  type Message,
  type PersonaSummary,
  type RoundEndData,
} from '../services/api'
import { useI18n } from '../i18n'

const API_BASE = '/api/v1/stakeholder'
const LOCAL_VIDEO_PREFIX = '[video-answer]'

export interface LocalVideoAttachment {
  url: string
  mimeType: string
  title?: string
  durationMs?: number
  size?: number
  recordedAt?: string
  trainingEvent?: {
    type: 'video_answer_submitted'
    trainingMode: 'video'
    schemaVersion: number
    reportDimensions: Array<'content_delivery' | 'camera_presence'>
    cameraPresenceStatus: 'placeholder'
  }
}

export interface UseChatReturn {
  selectedRoom: ChatRoomDetail | null
  setSelectedRoom: React.Dispatch<React.SetStateAction<ChatRoomDetail | null>>
  streamingContent: Record<string, string>
  dispatchSummary: DispatchPhase[] | null
  setDispatchSummary: React.Dispatch<React.SetStateAction<DispatchPhase[] | null>>
  dispatchExpanded: boolean
  setDispatchExpanded: React.Dispatch<React.SetStateAction<boolean>>
  sending: boolean
  sendError: string | null
  inputValue: string
  setInputValue: React.Dispatch<React.SetStateAction<string>>
  mentionQuery: string | null
  mentionResults: PersonaSummary[]
  setMentionQuery: React.Dispatch<React.SetStateAction<string | null>>
  setMentionResults: React.Dispatch<React.SetStateAction<PersonaSummary[]>>
  typingPersona: string | null
  streamingEntries: [string, string][]
  messageListRef: React.RefObject<HTMLDivElement | null>
  handleSend: (metadata?: Record<string, unknown>) => Promise<boolean>
  handleKeyDown: (e: React.KeyboardEvent) => void
  handleInputChange: (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    personaMap: Record<string, PersonaSummary>,
    roomType?: string,
    roomPersonaIds?: string[],
  ) => void
  insertMention: (persona: PersonaSummary) => void
  scrollToBottom: () => void
  loadRoomDetail: (roomId: number) => Promise<ChatRoomDetail | null>
  sendVideoAnswer: (attachment: LocalVideoAttachment, caption?: string) => Promise<boolean>
}

function serializeVideoMessage(attachment: LocalVideoAttachment, caption?: string): string {
  return `${caption?.trim() || 'Video answer'}\n\n${LOCAL_VIDEO_PREFIX}${JSON.stringify(attachment)}`
}

function hydrateLocalVideoMessage(message: Message): Message {
  if (!message.content.includes(LOCAL_VIDEO_PREFIX)) return message
  const markerIndex = message.content.indexOf(LOCAL_VIDEO_PREFIX)
  const caption = message.content.slice(0, markerIndex).trim()
  const raw = message.content.slice(markerIndex + LOCAL_VIDEO_PREFIX.length).trim()
  try {
    const attachment = JSON.parse(raw) as LocalVideoAttachment
    return {
      ...message,
      content: caption || 'Video answer',
      metadata: {
        ...(message.metadata || {}),
        videoUrl: attachment.url,
        mimeType: attachment.mimeType,
        title: attachment.title || 'Video answer',
        trainingEvent: attachment.trainingEvent,
      },
      attachments: [
        ...(message.attachments || []),
        {
          type: 'video',
          url: attachment.url,
          mimeType: attachment.mimeType,
          title: attachment.title || 'Video answer',
          durationMs: attachment.durationMs,
          size: attachment.size,
          recordedAt: attachment.recordedAt,
          trainingEvent: attachment.trainingEvent,
        },
      ],
    }
  } catch {
    return message
  }
}

function hydrateLocalVideoMessages(detail: ChatRoomDetail): ChatRoomDetail {
  return {
    ...detail,
    messages: detail.messages.map(hydrateLocalVideoMessage),
  }
}

export function useChat(
  roomId: number | null,
  options?: {
    onRoundEnd?: () => void
    audioPlayerRef?: React.RefObject<{ stop: () => void; isMuted: () => boolean; enqueue: (personaId: string, data: string, replyId?: string, sentenceIndex?: number) => void } | null>
  },
): UseChatReturn {
  const { tr } = useI18n()
  const [selectedRoom, setSelectedRoom] = useState<ChatRoomDetail | null>(null)
  const [streamingContent, setStreamingContent] = useState<Record<string, string>>({})
  const [dispatchSummary, setDispatchSummary] = useState<DispatchPhase[] | null>(null)
  const [dispatchExpanded, setDispatchExpanded] = useState(false)
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [inputValue, setInputValue] = useState('')
  const [typingPersona, setTypingPersona] = useState<string | null>(null)
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const [mentionResults, setMentionResults] = useState<PersonaSummary[]>([])

  const messageListRef = useRef<HTMLDivElement | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const eventSourceVersionRef = useRef(0)
  const pendingTypingPersonaRef = useRef<string | null>(null)

  const scrollToBottom = useCallback(() => {
    if (messageListRef.current) {
      messageListRef.current.scrollTop = messageListRef.current.scrollHeight
    }
  }, [])

  const setFallbackTyping = useCallback(() => {
    const fallbackPersonaId = selectedRoom?.room.persona_ids[0] || 'AI'
    pendingTypingPersonaRef.current = fallbackPersonaId
    setTypingPersona(fallbackPersonaId)
    setTimeout(scrollToBottom, 30)
  }, [scrollToBottom, selectedRoom])

  const clearPendingTyping = useCallback((personaId?: string) => {
    const pendingPersonaId = pendingTypingPersonaRef.current
    if (pendingPersonaId && (!personaId || pendingPersonaId === personaId)) {
      pendingTypingPersonaRef.current = null
      setTypingPersona((prev) => (prev === pendingPersonaId ? null : prev))
    }
  }, [])

  // SSE connection management
  useEffect(() => {
    if (!roomId) return

    // Close previous connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    const streamVersion = eventSourceVersionRef.current + 1
    eventSourceVersionRef.current = streamVersion
    const es = new EventSource(`${API_BASE}/rooms/${roomId}/stream`)
    eventSourceRef.current = es
    const isCurrentStream = () =>
      eventSourceRef.current === es && eventSourceVersionRef.current === streamVersion

    es.addEventListener('message', (e) => {
      if (!isCurrentStream()) return
      const msg: Message = hydrateLocalVideoMessage(JSON.parse(e.data))
      // Clear streaming content for this persona -- the final message replaces it
      if (msg.sender_type === 'persona') {
        clearPendingTyping(msg.sender_id)
        setTypingPersona((prev) => (prev === msg.sender_id ? null : prev))
        setStreamingContent((prev) => {
          const next = { ...prev }
          delete next[msg.sender_id]
          return next
        })
      }
      setSelectedRoom((prev) => {
        if (!prev || prev.room.id !== msg.room_id) return prev
        // Avoid duplicates
        const exists = prev.messages.some((m) => m.id === msg.id)
        if (exists) return prev
        return { ...prev, messages: [...prev.messages, msg] }
      })
      setTimeout(scrollToBottom, 50)
    })

    es.addEventListener('streaming_delta', (e) => {
      if (!isCurrentStream()) return
      const data: { persona_id: string; delta: string } = JSON.parse(e.data)
      clearPendingTyping()
      setTypingPersona((prev) => (prev === data.persona_id ? null : prev))
      setStreamingContent((prev) => ({
        ...prev,
        [data.persona_id]: (prev[data.persona_id] || '') + data.delta,
      }))
      setTimeout(scrollToBottom, 30)
    })

    es.addEventListener('typing', (e) => {
      if (!isCurrentStream()) return
      const data = JSON.parse(e.data)
      clearPendingTyping()
      if (data.status === 'start') {
        setTypingPersona(data.persona_id)
      } else {
        setTypingPersona(null)
        // Fallback cleanup of streaming content
        setStreamingContent((prev) => {
          const next = { ...prev }
          delete next[data.persona_id]
          return next
        })
      }
    })

    es.addEventListener('audio_chunk', (e) => {
      if (!isCurrentStream()) return
      const player = options?.audioPlayerRef?.current
      if (player && !player.isMuted()) {
        const data = JSON.parse(e.data)
        if (data.data) {
          player.enqueue(
            data.persona_id, data.data, data.reply_id, data.sentence_index,
          )
        }
      }
    })

    es.addEventListener('round_end', (e) => {
      if (!isCurrentStream()) return
      pendingTypingPersonaRef.current = null
      setTypingPersona(null)
      setStreamingContent({})
      try {
        const data: RoundEndData = JSON.parse(e.data)
        if (data.dispatch_log && data.dispatch_log.length > 0) {
          setDispatchSummary(data.dispatch_log)
          setDispatchExpanded(false)
        }
      } catch {
        // Backward compat: old backend may send empty payload
      }
    })

    es.onerror = () => {
      if (!isCurrentStream()) return
      pendingTypingPersonaRef.current = null
      setTypingPersona(null)
    }

    return () => {
      eventSourceVersionRef.current += 1
      es.close()
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null
      }
      pendingTypingPersonaRef.current = null
      setTypingPersona(null)
      setStreamingContent({})
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId])

  const loadRoomDetail = useCallback(async (id: number): Promise<ChatRoomDetail | null> => {
    try {
      const detail = await fetchRoomDetail(id)
      const hydrated = hydrateLocalVideoMessages(detail)
      setSelectedRoom(hydrated)
      setTimeout(scrollToBottom, 50)
      return hydrated
    } catch {
      setSelectedRoom(null)
      return null
    }
  }, [scrollToBottom])

  const handleSend = useCallback(async (metadata?: Record<string, unknown>): Promise<boolean> => {
    const content = inputValue.trim()
    if (!content || !roomId || sending) return false

    // Stop any playing audio when user sends a new message
    options?.audioPlayerRef?.current?.stop()

    setSending(true)
    setSendError(null)
    setInputValue('')
    setMentionQuery(null)
    setMentionResults([])
    setDispatchSummary(null)

    try {
      await apiSendMessage(roomId, content, metadata)
      setFallbackTyping()
      setTimeout(scrollToBottom, 100)
      return true
    } catch (e) {
      console.error('Send failed:', e)
      setInputValue(content)
      setSendError(tr('消息发送失败，请稍后重试。', 'Message failed to send. Please try again.'))
      // Fallback: refresh room detail
      if (roomId) {
        try {
          const detail = await fetchRoomDetail(roomId)
          setSelectedRoom(hydrateLocalVideoMessages(detail))
          setTimeout(scrollToBottom, 50)
        } catch (refreshError) {
          console.error('Refresh after send failure failed:', refreshError)
        }
      }
      return false
    } finally {
      setSending(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputValue, roomId, sending, scrollToBottom, setFallbackTyping, tr])

  const sendVideoAnswer = useCallback(async (
    attachment: LocalVideoAttachment,
    caption = inputValue,
  ): Promise<boolean> => {
    if (!roomId || sending) return false
    options?.audioPlayerRef?.current?.stop()
    setSending(true)
    setSendError(null)
    setInputValue('')
    setMentionQuery(null)
    setMentionResults([])
    setDispatchSummary(null)
    try {
      await apiSendMessage(roomId, serializeVideoMessage(attachment, caption))
      setFallbackTyping()
      try {
        const detail = await fetchRoomDetail(roomId)
        setSelectedRoom(hydrateLocalVideoMessages(detail))
      } catch (refreshError) {
        console.error('Refresh after video send failed:', refreshError)
      }
      setTimeout(scrollToBottom, 100)
      return true
    } catch (e) {
      console.error('Video send failed:', e)
      setInputValue(caption)
      setSendError(tr('视频消息发送失败，请稍后重试。', 'Video message failed to send. Please try again.'))
      return false
    } finally {
      setSending(false)
    }
  }, [inputValue, options?.audioPlayerRef, roomId, scrollToBottom, sending, setFallbackTyping, tr])

  const insertMention = useCallback((persona: PersonaSummary) => {
    setInputValue((prev) =>
      prev.replace(/@[\w\u4e00-\u9fff]*$/, `@${persona.name} `),
    )
    setMentionQuery(null)
    setMentionResults([])
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      // If mention dropdown is visible, don't send -- let user pick
      if (mentionQuery !== null && mentionResults.length > 0) {
        e.preventDefault()
        insertMention(mentionResults[0])
        return
      }
      e.preventDefault()
      handleSend()
    }
  }, [mentionQuery, mentionResults, insertMention, handleSend])

  const handleInputChange = useCallback((
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    personaMap: Record<string, PersonaSummary>,
    roomType?: string,
    roomPersonaIds?: string[],
  ) => {
    const val = e.target.value
    setInputValue(val)
    if (sendError) setSendError(null)

    const atMatch = val.match(/@([\w\u4e00-\u9fff]*)$/)
    if (atMatch && roomType === 'group') {
      const query = atMatch[1].toLowerCase()
      const roomPids = new Set(roomPersonaIds || [])
      const matches = Object.values(personaMap).filter(
        (p) =>
          roomPids.has(p.id) &&
          (p.name.toLowerCase().includes(query) ||
          p.id.toLowerCase().includes(query)),
      )
      setMentionQuery(atMatch[1])
      setMentionResults(matches)
    } else {
      setMentionQuery(null)
      setMentionResults([])
    }
  }, [sendError])

  const streamingEntries = Object.entries(streamingContent) as [string, string][]

  return {
    selectedRoom,
    setSelectedRoom,
    streamingContent,
    dispatchSummary,
    setDispatchSummary,
    dispatchExpanded,
    setDispatchExpanded,
    sending,
    sendError,
    inputValue,
    setInputValue,
    mentionQuery,
    mentionResults,
    setMentionQuery,
    setMentionResults,
    typingPersona,
    streamingEntries,
    messageListRef,
    handleSend,
    handleKeyDown,
    handleInputChange,
    insertMention,
    scrollToBottom,
    loadRoomDetail,
    sendVideoAnswer,
  }
}
