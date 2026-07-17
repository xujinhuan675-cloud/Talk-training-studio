import React from 'react'
import Markdown from 'react-markdown'
import { ListTree, MapPin, MessageCircle, ClipboardList, Route, Search, Volume2, Video, Loader2 } from 'lucide-react'
import Avatar from '../Avatar'
import type { Message, DispatchPhase, PersonaSummary } from '../../services/api'
import {
  buildConversationTreeMessageActionContext,
  fetchConversationTreeBranchSnapshot,
  type ConversationTreeBranchSnapshot,
  type ConversationTreeActionKind,
  type ConversationTreeMessageActionContext,
  type ConversationTreeMessage,
} from '../../services/trainingConversation'
import { useI18n } from '../../i18n'
import './MessageList.css'

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatTime(ts: string | null, locale: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
}

/** Highlight @mentions inside a plain text string */
function highlightMentions(text: string): React.ReactNode {
  const parts = text.split(/(@[\w\u4e00-\u9fff]+)/g)
  if (parts.length === 1) return text
  return parts.map((part, i) =>
    part.startsWith('@') ? (
      <span key={i} className="mention-highlight">{part}</span>
    ) : (
      part
    ),
  )
}

/** Recursively walk React children, applying @mention highlights to string nodes */
function withMentions(children: React.ReactNode): React.ReactNode {
  if (typeof children === 'string') return highlightMentions(children)
  if (Array.isArray(children)) {
    return children.map((child, i) =>
      typeof child === 'string'
        ? <React.Fragment key={i}>{highlightMentions(child)}</React.Fragment>
        : child,
    )
  }
  return children
}

/** Render message content as Markdown with @mention highlights */
function renderContent(text: string) {
  return (
    <Markdown
      components={{
        p: ({ children }) => <p>{withMentions(children)}</p>,
        li: ({ children }) => <li>{withMentions(children)}</li>,
      }}
    >
      {text}
    </Markdown>
  )
}

type MessageWithMedia = Message & {
  metadata?: unknown
  attachments?: unknown
  video_url?: unknown
  videoUrl?: unknown
  mediaUrl?: unknown
  media_url?: unknown
}

interface VideoAttachment {
  url: string
  mimeType?: string
  title?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}

function normalizeVideoCandidate(value: unknown): VideoAttachment | null {
  if (typeof value === 'string' && value.trim()) {
    return { url: value }
  }

  if (!isRecord(value)) return null

  const type = stringValue(value.type) || stringValue(value.kind) || stringValue(value.mediaType)
  const mimeType = stringValue(value.mime_type) || stringValue(value.mimeType) || stringValue(value.contentType)
  const url =
    stringValue(value.video_url) ||
    stringValue(value.videoUrl) ||
    stringValue(value.mediaUrl) ||
    stringValue(value.media_url) ||
    stringValue(value.url) ||
    stringValue(value.href)

  if (!url) return null
  if (type && type !== 'video' && !type.startsWith('video/')) return null
  if (mimeType && !mimeType.startsWith('video/')) return null

  return {
    url,
    mimeType,
    title: stringValue(value.title) || stringValue(value.name) || stringValue(value.filename),
  }
}

function findVideoAttachment(message: Message): VideoAttachment | null {
  const marker = '[video-answer]'
  if (message.content.includes(marker)) {
    const raw = message.content.slice(message.content.indexOf(marker) + marker.length).trim()
    try {
      const parsed = JSON.parse(raw)
      const attachment = normalizeVideoCandidate({ ...parsed, type: 'video' })
      if (attachment) return attachment
    } catch {
      // Ignore malformed local marker and render the text normally.
    }
  }

  const msg = message as MessageWithMedia
  const direct = normalizeVideoCandidate({
    video_url: msg.video_url,
    videoUrl: msg.videoUrl,
    mediaUrl: msg.mediaUrl,
    media_url: msg.media_url,
  })
  if (direct) return direct

  const containers = [msg.metadata, msg.attachments]
  for (const container of containers) {
    const directContainer = normalizeVideoCandidate(container)
    if (directContainer) return directContainer

    if (Array.isArray(container)) {
      for (const item of container) {
        const attachment = normalizeVideoCandidate(item)
        if (attachment) return attachment
      }
    }

    if (isRecord(container)) {
      const nestedDirect = normalizeVideoCandidate({
        video_url: container.video_url,
        videoUrl: container.videoUrl,
        mediaUrl: container.mediaUrl,
        media_url: container.media_url,
        url: container.url,
        mimeType: container.mimeType,
        mime_type: container.mime_type,
        type: container.type,
        title: container.title,
      })
      if (nestedDirect) return nestedDirect

      const nested = container.attachments || container.media || container.video
      if (Array.isArray(nested)) {
        for (const item of nested) {
          const attachment = normalizeVideoCandidate(item)
          if (attachment) return attachment
        }
      } else {
        const attachment = normalizeVideoCandidate(nested)
        if (attachment) return attachment
      }
    }
  }

  return null
}

function renderVideoAttachment(attachment: VideoAttachment | null) {
  if (!attachment) return null

  return (
    <div className="message-video-attachment">
      {attachment.title && (
        <div className="message-video-title">
          <Video size={14} />
          <span>{attachment.title}</span>
        </div>
      )}
      <video className="message-video" controls preload="metadata" src={attachment.url}>
        {attachment.mimeType && <source src={attachment.url} type={attachment.mimeType} />}
      </video>
    </div>
  )
}

type MessageTreeActionLabels = {
  group: string
  title: string
  readonlyBadge: string
  hint: string
  branchLabel: string
  noBranch: string
  searchQueryLabel: string
  selectedBadge: string
  focus: string
  focusDesc: string
  path: string
  pathDesc: string
  children: string
  childrenDesc: string
  search: string
  searchDesc: string
  searchPlaceholder: string
  loading: string
  error: string
  currentPath: string
  childBranches: string
  searchResults: string
  selectPath: string
  noPath: string
  noChildren: string
  noSearchResults: string
  roleUser: string
  roleAssistant: string
  roleSystem: string
  statusLabel: string
}

export interface MessageTreePathSelection {
  provider: string
  conversationId: string
  selectedMessageId: string
  branchId: string | null
  path: ConversationTreeMessage[]
  sourceMessageId: number | null
}

function messageSearchQuery(message: Message, context: ConversationTreeMessageActionContext): string {
  const text = message.content
    .replace(/\[video-answer\]\s*\{[\s\S]*$/u, '')
    .replace(/\s+/g, ' ')
    .trim()

  return text.slice(0, 80) || context.messagePublicId
}

function getMessageTreeActionContext(message: Message): ConversationTreeMessageActionContext | null {
  return buildConversationTreeMessageActionContext({ metadata: message.metadata ?? null })
}

function buildMessageTreeSelection(
  snapshot: ConversationTreeBranchSnapshot,
  context: ConversationTreeMessageActionContext,
  sourceMessageId: number | null,
): MessageTreePathSelection | null {
  const selectedMessage = snapshot.message ?? snapshot.path[snapshot.path.length - 1]
  if (!selectedMessage) return null

  return {
    provider: context.provider,
    conversationId: context.conversationId,
    selectedMessageId: selectedMessage.publicId,
    branchId: selectedMessage.branchId ?? context.branchId,
    path: snapshot.path.length > 0 ? snapshot.path : [selectedMessage],
    sourceMessageId,
  }
}

function contextForTreeMessage(
  baseContext: ConversationTreeMessageActionContext,
  message: ConversationTreeMessage,
): ConversationTreeMessageActionContext | null {
  return buildConversationTreeMessageActionContext({
    provider: baseContext.provider,
    conversationId: baseContext.conversationId,
    messagePublicId: message.publicId,
    branchId: message.branchId ?? baseContext.branchId,
  })
}

function treeMessagePreview(message: ConversationTreeMessage): string {
  const text = message.content.replace(/\s+/g, ' ').trim()
  return text.length > 96 ? `${text.slice(0, 95)}...` : text || message.publicId
}

function treeRoleLabel(role: string, labels: MessageTreeActionLabels): string {
  const normalized = role.toLowerCase()
  if (normalized === 'assistant' || normalized === 'persona') return labels.roleAssistant
  if (normalized === 'system') return labels.roleSystem
  return labels.roleUser
}

function MessageTreeItem({
  message,
  labels,
  active,
  onSelect,
}: {
  message: ConversationTreeMessage
  labels: MessageTreeActionLabels
  active: boolean
  onSelect: (message: ConversationTreeMessage) => void
}) {
  const preview = treeMessagePreview(message)
  return (
    <button
      type="button"
      className={`message-tree-node${active ? ' active' : ''}`}
      onClick={(event) => {
        event.stopPropagation()
        onSelect(message)
      }}
      title={preview}
      aria-label={`${labels.selectPath}: ${preview}`}
    >
      <span className="message-tree-node-role">{treeRoleLabel(message.role, labels)}</span>
      <span className="message-tree-node-preview">{preview}</span>
      <span className="message-tree-node-meta">
        <span>{message.branchId ?? labels.noBranch}</span>
        <span>{labels.statusLabel}: {message.status}</span>
      </span>
    </button>
  )
}

interface MessageTreeActionsProps {
  message: Message,
  context: ConversationTreeMessageActionContext,
  labels: MessageTreeActionLabels,
  selectedTreeNodeId?: string | null
  onSelectPath?: (selection: MessageTreePathSelection) => void
}

function MessageTreeActions({
  message,
  context,
  labels,
  selectedTreeNodeId,
  onSelectPath,
}: MessageTreeActionsProps) {
  const [expanded, setExpanded] = React.useState(false)
  const [focusedContext, setFocusedContext] = React.useState(context)
  const [snapshot, setSnapshot] = React.useState<ConversationTreeBranchSnapshot | null>(null)
  const [loadingAction, setLoadingAction] = React.useState<'focus' | 'children' | 'search' | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const searchQuery = messageSearchQuery(message, context)
  const {
    availableActions,
    branchId,
    conversationId,
    endpoints,
    messagePublicId,
    provider,
  } = context
  const {
    children: childrenEndpoint,
    edit: editEndpoint,
    fork: forkEndpoint,
    locate: locateEndpoint,
    path: pathEndpoint,
    retry: retryEndpoint,
    search: searchEndpoint,
  } = endpoints
  const availableActionsKey = availableActions.join('|')
  const resetContext = React.useMemo<ConversationTreeMessageActionContext>(() => ({
    availableActions: availableActionsKey
      .split('|')
      .filter(Boolean) as ConversationTreeActionKind[],
    branchId,
    conversationId,
    endpoints: {
      children: childrenEndpoint,
      edit: editEndpoint,
      fork: forkEndpoint,
      locate: locateEndpoint,
      path: pathEndpoint,
      retry: retryEndpoint,
      search: searchEndpoint,
    },
    messagePublicId,
    provider,
  }), [
    availableActionsKey,
    branchId,
    childrenEndpoint,
    conversationId,
    editEndpoint,
    forkEndpoint,
    locateEndpoint,
    messagePublicId,
    pathEndpoint,
    provider,
    retryEndpoint,
    searchEndpoint,
  ])
  const [searchText, setSearchText] = React.useState(searchQuery)
  const requestSeqRef = React.useRef(0)
  const selectedPathIds = React.useMemo(
    () => new Set(snapshot?.path.map((item) => item.publicId) ?? []),
    [snapshot],
  )

  React.useEffect(() => {
    setFocusedContext(resetContext)
    setSnapshot(null)
    setError(null)
    setSearchText(searchQuery)
  }, [resetContext, searchQuery])

  React.useEffect(() => () => {
    requestSeqRef.current += 1
  }, [])

  const loadSnapshot = React.useCallback(async (
    nextContext: ConversationTreeMessageActionContext,
    action: 'focus' | 'children' | 'search',
    query: string | null,
  ) => {
    const requestSeq = requestSeqRef.current + 1
    requestSeqRef.current = requestSeq
    setExpanded(true)
    setLoadingAction(action)
    setError(null)
    try {
      const nextSnapshot = await fetchConversationTreeBranchSnapshot(nextContext, {
        branchId: nextContext.branchId,
        searchQuery: query,
      })
      if (requestSeqRef.current !== requestSeq) return
      setFocusedContext(nextContext)
      setSnapshot(nextSnapshot)
      const selection = buildMessageTreeSelection(nextSnapshot, nextContext, message.id)
      if (selection) onSelectPath?.(selection)
    } catch (err) {
      if (requestSeqRef.current !== requestSeq) return
      console.error('Failed to load message tree branch data:', err)
      setError(labels.error)
    } finally {
      if (requestSeqRef.current === requestSeq) {
        setLoadingAction(null)
      }
    }
  }, [labels.error, message.id, onSelectPath])

  const handleSelectTreeMessage = React.useCallback((treeMessage: ConversationTreeMessage) => {
    const nextContext = contextForTreeMessage(focusedContext, treeMessage)
    if (!nextContext) return
    void loadSnapshot(nextContext, 'children', searchText.trim() || null)
  }, [focusedContext, loadSnapshot, searchText])

  const handleSubmitSearch = React.useCallback((event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    event.stopPropagation()
    void loadSnapshot(focusedContext, 'search', searchText.trim() || searchQuery)
  }, [focusedContext, loadSnapshot, searchQuery, searchText])

  const hasSnapshot = Boolean(snapshot)
  const currentNodeId = snapshot?.message?.publicId ?? focusedContext.messagePublicId
  const isSelectedCurrentNode = selectedTreeNodeId === focusedContext.messagePublicId
    || selectedTreeNodeId === currentNodeId

  return (
    <section className="message-tree-actions" aria-label={labels.group}>
      <div className="message-tree-actions-header">
        <span className="message-tree-actions-title">
          <ListTree size={14} aria-hidden="true" />
          {labels.title}
        </span>
        <span className="message-tree-badges">
          {isSelectedCurrentNode && <span className="message-tree-selected-badge">{labels.selectedBadge}</span>}
          <span className="message-tree-readonly-badge">{labels.readonlyBadge}</span>
        </span>
      </div>
      <p className="message-tree-actions-hint">{labels.hint}</p>
      <div className="message-tree-meta" aria-label={labels.branchLabel}>
        <span className="message-tree-meta-item">
          <span className="message-tree-meta-label">{labels.branchLabel}</span>
          <span className="message-tree-meta-value">{focusedContext.branchId ?? labels.noBranch}</span>
        </span>
        <span className="message-tree-meta-item">
          <span className="message-tree-meta-label">{labels.searchQueryLabel}</span>
          <span className="message-tree-meta-value">{searchText || searchQuery}</span>
        </span>
      </div>
      <div className="message-tree-action-links">
        <button
          type="button"
          className="message-tree-action"
          title={labels.focusDesc}
          onClick={(event) => {
            event.stopPropagation()
            void loadSnapshot(focusedContext, 'focus', null)
          }}
        >
          <span className="message-tree-action-icon" aria-hidden="true">
            {loadingAction === 'focus' ? <Loader2 size={13} className="spin" /> : <MapPin size={13} />}
          </span>
          <span className="message-tree-action-copy">
            <span className="message-tree-action-label">{labels.focus}</span>
            <span className="message-tree-action-description">{labels.focusDesc}</span>
          </span>
        </button>
        <button
          type="button"
          className="message-tree-action"
          title={labels.childrenDesc}
          onClick={(event) => {
            event.stopPropagation()
            void loadSnapshot(focusedContext, 'children', null)
          }}
        >
          <span className="message-tree-action-icon" aria-hidden="true">
            {loadingAction === 'children' ? <Loader2 size={13} className="spin" /> : <ListTree size={13} />}
          </span>
          <span className="message-tree-action-copy">
            <span className="message-tree-action-label">{labels.children}</span>
            <span className="message-tree-action-description">{labels.childrenDesc}</span>
          </span>
        </button>
        <form className="message-tree-search-form" onSubmit={handleSubmitSearch}>
          <label>
            <span className="sr-only">{labels.searchPlaceholder}</span>
            <input
              value={searchText}
              onClick={(event) => event.stopPropagation()}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder={labels.searchPlaceholder}
            />
          </label>
          <button
            type="submit"
            title={labels.searchDesc}
            onClick={(event) => event.stopPropagation()}
          >
            {loadingAction === 'search' ? <Loader2 size={13} className="spin" /> : <Search size={13} />}
            <span>{labels.search}</span>
          </button>
        </form>
      </div>
      {loadingAction && <div className="message-tree-status">{labels.loading}</div>}
      {error && <div className="message-tree-error">{error}</div>}
      {expanded && !loadingAction && !error && (
        <div className="message-tree-branch-panel">
          <div className="message-tree-section">
            <div className="message-tree-section-title">
              <Route size={13} aria-hidden="true" />
              <span>{labels.currentPath}</span>
            </div>
            {hasSnapshot && snapshot?.path.length ? (
              <div className="message-tree-path-list">
                {snapshot.path.map((pathMessage) => (
                  <MessageTreeItem
                    key={pathMessage.publicId}
                    message={pathMessage}
                    labels={labels}
                    active={selectedTreeNodeId === pathMessage.publicId || currentNodeId === pathMessage.publicId}
                    onSelect={handleSelectTreeMessage}
                  />
                ))}
              </div>
            ) : (
              <div className="message-tree-empty">{labels.noPath}</div>
            )}
          </div>
          <div className="message-tree-section">
            <div className="message-tree-section-title">
              <ListTree size={13} aria-hidden="true" />
              <span>{labels.childBranches}</span>
            </div>
            {hasSnapshot && snapshot?.children.length ? (
              <div className="message-tree-node-list">
                {snapshot.children.map((child) => (
                  <MessageTreeItem
                    key={child.publicId}
                    message={child}
                    labels={labels}
                    active={selectedPathIds.has(child.publicId) || selectedTreeNodeId === child.publicId}
                    onSelect={handleSelectTreeMessage}
                  />
                ))}
              </div>
            ) : (
              <div className="message-tree-empty">{labels.noChildren}</div>
            )}
          </div>
          {snapshot?.searchResults.length ? (
            <div className="message-tree-section">
              <div className="message-tree-section-title">
                <Search size={13} aria-hidden="true" />
                <span>{labels.searchResults}</span>
              </div>
              <div className="message-tree-node-list">
                {snapshot.searchResults.map((result) => (
                  <MessageTreeItem
                    key={result.message.publicId}
                    message={result.message}
                    labels={labels}
                    active={selectedTreeNodeId === result.message.publicId}
                    onSelect={handleSelectTreeMessage}
                  />
                ))}
              </div>
            </div>
          ) : loadingAction !== 'search' && hasSnapshot && searchText.trim() ? (
            <div className="message-tree-empty">{labels.noSearchResults}</div>
          ) : null}
        </div>
      )}
    </section>
  )
}

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

export interface MessageListProps {
  messages: Message[]
  streamingEntries: [string, string][]
  highlightedMessageId: number | null
  personaMap: Record<string, PersonaSummary>
  /** ref forwarded to the scrollable container */
  listRef: React.RefObject<HTMLDivElement | null>
  /** Dispatch transparency metadata */
  dispatchSummary: DispatchPhase[] | null
  dispatchExpanded: boolean
  onToggleDispatch: () => void
  /** Typing / voice indicators */
  typingPersona: string | null
  playingPersonaId: string | null
  currentTreeSelection?: MessageTreePathSelection | null
  onSelectTreePath?: (selection: MessageTreePathSelection) => void
  /** Close export menu on click inside message list */
  onClick?: () => void
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function MessageList({
  messages,
  streamingEntries,
  highlightedMessageId,
  personaMap,
  listRef,
  dispatchSummary,
  dispatchExpanded,
  onToggleDispatch,
  typingPersona,
  playingPersonaId,
  currentTreeSelection,
  onSelectTreePath,
  onClick,
}: MessageListProps) {
  const { t, tr, locale } = useI18n()
  const isEmpty = messages.length === 0 && streamingEntries.length === 0
  const currentTreePathIds = React.useMemo(
    () => new Set(currentTreeSelection?.path.map((item) => item.publicId) ?? []),
    [currentTreeSelection],
  )
  const messageTreeActionLabels: MessageTreeActionLabels = {
    group: t('messageTree.actions.group'),
    title: t('messageTree.actions.title'),
    readonlyBadge: t('messageTree.actions.readonlyBadge'),
    hint: t('messageTree.actions.hint'),
    branchLabel: t('messageTree.actions.branchLabel'),
    noBranch: t('messageTree.actions.noBranch'),
    searchQueryLabel: t('messageTree.actions.searchQueryLabel'),
    selectedBadge: t('messageTree.actions.selectedBadge'),
    focus: t('messageTree.actions.focus'),
    focusDesc: t('messageTree.actions.focusDesc'),
    path: t('messageTree.actions.path'),
    pathDesc: t('messageTree.actions.pathDesc'),
    children: t('messageTree.actions.children'),
    childrenDesc: t('messageTree.actions.childrenDesc'),
    search: t('messageTree.actions.search'),
    searchDesc: t('messageTree.actions.searchDesc'),
    searchPlaceholder: t('messageTree.actions.searchPlaceholder'),
    loading: t('messageTree.actions.loading'),
    error: t('messageTree.actions.error'),
    currentPath: t('messageTree.actions.currentPath'),
    childBranches: t('messageTree.actions.childBranches'),
    searchResults: t('messageTree.actions.searchResults'),
    selectPath: t('messageTree.actions.selectPath'),
    noPath: t('messageTree.actions.noPath'),
    noChildren: t('messageTree.actions.noChildren'),
    noSearchResults: t('messageTree.actions.noSearchResults'),
    roleUser: t('messageTree.actions.roleUser'),
    roleAssistant: t('messageTree.actions.roleAssistant'),
    roleSystem: t('messageTree.actions.roleSystem'),
    statusLabel: t('messageTree.actions.statusLabel'),
  }

  React.useEffect(() => {
    if (!typingPersona && !playingPersonaId && streamingEntries.length === 0) return
    const el = listRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [listRef, playingPersonaId, streamingEntries.length, typingPersona])

  return (
    <div className="message-list" ref={listRef} onClick={onClick}>
      {isEmpty ? (
        <div className="empty-messages">
          <MessageCircle size={36} strokeWidth={1.2} />
          <p>{tr('发送第一条消息，开始模拟对话', 'Send the first message to start the simulation')}</p>
        </div>
      ) : (
        <>
          {messages.map((msg) => {
            const persona = msg.sender_type === 'persona' ? personaMap[msg.sender_id] : null
            const borderColor = persona?.avatar_color || undefined
            const videoAttachment = findVideoAttachment(msg)
            const messageTreeActionContext = getMessageTreeActionContext(msg)
            const isInSelectedTreePath = messageTreeActionContext
              ? currentTreePathIds.has(messageTreeActionContext.messagePublicId)
              : false
            const isSelectedTreeNode = Boolean(
              messageTreeActionContext
              && currentTreeSelection?.selectedMessageId === messageTreeActionContext.messagePublicId,
            )
            return (
              <div
                key={msg.id}
                id={`msg-${msg.id}`}
                className={`message ${msg.sender_type}${highlightedMessageId === msg.id ? ' highlighted' : ''}${isInSelectedTreePath ? ' tree-path-selected' : ''}${isSelectedTreeNode ? ' tree-node-selected' : ''}`}
                data-sender={msg.sender_type}
              >
                {msg.sender_type === 'persona' && (
                  <div className="message-row">
                    <Avatar name={persona?.name || msg.sender_id} color={borderColor || '#2D9C6F'} size={28} />
                    <div className="message-content">
                      <div className="sender-name" style={borderColor ? { color: borderColor } : undefined}>
                        {persona?.name || msg.sender_id}
                        {msg.emotion_label && (
                          <span className={`emotion-tag ${(msg.emotion_score ?? 0) > 0 ? 'positive' : (msg.emotion_score ?? 0) < 0 ? 'negative' : 'neutral'}`}>
                            {msg.emotion_label}
                          </span>
                        )}
                      </div>
                      <div
                        className="message-bubble"
                        style={borderColor ? { borderLeft: `2px solid ${borderColor}` } : undefined}
                      >
                        {renderContent(msg.content)}
                        {renderVideoAttachment(videoAttachment)}
                      </div>
                      {messageTreeActionContext && (
                        <MessageTreeActions
                          message={msg}
                          context={messageTreeActionContext}
                          labels={messageTreeActionLabels}
                          selectedTreeNodeId={currentTreeSelection?.selectedMessageId}
                          onSelectPath={onSelectTreePath}
                        />
                      )}
                      <div className="message-time">{formatTime(msg.timestamp, locale === 'zh' ? 'zh-CN' : 'en-US')}</div>
                    </div>
                  </div>
                )}
                {msg.sender_type === 'user' && (
                  <>
                    <div className="message-bubble">
                      {renderContent(msg.content)}
                      {renderVideoAttachment(videoAttachment)}
                    </div>
                    {messageTreeActionContext && (
                      <MessageTreeActions
                        message={msg}
                        context={messageTreeActionContext}
                        labels={messageTreeActionLabels}
                        selectedTreeNodeId={currentTreeSelection?.selectedMessageId}
                        onSelectPath={onSelectTreePath}
                      />
                    )}
                    <div className="message-time">{formatTime(msg.timestamp, locale === 'zh' ? 'zh-CN' : 'en-US')}</div>
                  </>
                )}
                {msg.sender_type === 'system' && (
                  <>
                    <div className="message-bubble">
                      {renderContent(msg.content)}
                      {renderVideoAttachment(videoAttachment)}
                    </div>
                    {messageTreeActionContext && (
                      <MessageTreeActions
                        message={msg}
                        context={messageTreeActionContext}
                        labels={messageTreeActionLabels}
                        selectedTreeNodeId={currentTreeSelection?.selectedMessageId}
                        onSelectPath={onSelectTreePath}
                      />
                    )}
                  </>
                )}
              </div>
            )
          })}

          {/* Streaming messages -- in-progress persona replies */}
          {streamingEntries.map(([personaId, text]) => {
            const persona = personaMap[personaId]
            const borderColor = persona?.avatar_color || undefined
            return (
              <div key={`streaming-${personaId}`} className="message persona streaming" data-sender="persona">
                <div className="message-row">
                  <Avatar name={persona?.name || personaId} color={borderColor || '#2D9C6F'} size={28} />
                  <div className="message-content">
                    <div className="sender-name" style={borderColor ? { color: borderColor } : undefined}>
                      {persona?.name || personaId}
                    </div>
                    <div
                      className="message-bubble"
                      style={borderColor ? { borderLeft: `2px solid ${borderColor}` } : undefined}
                    >
                      {renderContent(text)}
                      <span className="streaming-cursor" />
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </>
      )}

      {/* Dispatcher transparency: collapsible dispatch summary */}
      {dispatchSummary && dispatchSummary.length > 0 && (
        <div className="dispatch-summary" onClick={onToggleDispatch}>
          <div className="dispatch-summary-header">
            <ClipboardList size={15} className="dispatch-summary-icon" />
            <span>
              {tr('本轮 {count} 位角色参与讨论', '{count} personas joined this round', {
                count: dispatchSummary.reduce((n, p) => n + p.responders.length, 0),
              })}
            </span>
            <span className={`dispatch-expand-arrow ${dispatchExpanded ? 'expanded' : ''}`}>&#9662;</span>
          </div>
          {dispatchExpanded && (
            <div className="dispatch-summary-body">
              {dispatchSummary.map((phase, i) => (
                <div key={i} className="dispatch-phase">
                  <div className="dispatch-phase-label">
                    {phase.phase === 'initial'
                      ? tr('初始响应', 'Initial response')
                      : phase.trigger_persona_id
                        ? tr('跟进讨论（由 {name} 触发）', 'Follow-up discussion triggered by {name}', {
                          name: personaMap[phase.trigger_persona_id]?.name || phase.trigger_persona_id,
                        })
                        : tr('跟进讨论', 'Follow-up discussion')}
                  </div>
                  <ul className="dispatch-responders">
                    {phase.responders.map((r) => (
                      <li key={r.persona_id}>
                        <strong style={{ color: personaMap[r.persona_id]?.avatar_color || undefined }}>
                          {personaMap[r.persona_id]?.name || r.persona_id}
                        </strong>
                        {' — '}
                        {r.reason || tr('参与讨论', 'Joined the discussion')}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {typingPersona && streamingEntries.length === 0 && (
        <div className="message persona typing-message" data-sender="persona" aria-live="polite">
          <div className="message-bubble typing-bubble">
            <span className="typing-dots" aria-hidden="true"><span /><span /><span /></span>
            <span className="typing-label">
          {tr('{name} 正在回复', '{name} is replying', { name: personaMap[typingPersona]?.name || typingPersona })}
            </span>
          </div>
        </div>
      )}

      {playingPersonaId && !typingPersona && (
        <div className="typing-indicator">
          <Volume2 size={14} />
          &nbsp;{tr('{name} 正在播放语音', '{name} is playing voice', { name: personaMap[playingPersonaId]?.name || playingPersonaId })}
        </div>
      )}
    </div>
  )
}
