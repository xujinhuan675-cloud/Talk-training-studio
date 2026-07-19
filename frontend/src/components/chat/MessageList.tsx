import React from 'react'
import Markdown from 'react-markdown'
import {
  Check,
  ChevronDown,
  GitFork,
  ListTree,
  Loader2,
  MapPin,
  MessageCircle,
  ClipboardList,
  PencilLine,
  RotateCw,
  Route,
  Search,
  Volume2,
  Video,
} from 'lucide-react'
import Avatar from '../Avatar'
import type { Message, DispatchPhase, PersonaSummary } from '../../services/api'
import {
  applyConversationTreeMessageAction,
  buildConversationTreeMessageActionContext,
  fetchConversationTreeBranchSnapshot,
  getMessageActionResultPath,
  type ConversationTreeBranchSnapshot,
  type ConversationTreeActionKind,
  type ConversationTreeMessageActionContext,
  type ConversationTreeMessage,
  type ConversationTreeMessageWriteActionKind,
  type MessageActionForkOption,
  type MessageActionResult,
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
  controlledBadge: string
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
  currentNode: string
  tailNode: string
  forkPoint: string
  noForkPoint: string
  currentSelection: string
  selectionCurrent: string
  selectionInPath: string
  selectionHint: string
  pathNodeCount: string
  writeTarget: string
  writeTargetDesc: string
  keptCurrentPath: string
  newTail: string
  roleUser: string
  roleAssistant: string
  roleSystem: string
  statusLabel: string
  writesTitle: string
  writesToggle: string
  writesToggleOpen: string
  edit: string
  editDesc: string
  editContentLabel: string
  editPlaceholder: string
  retry: string
  retryDesc: string
  retryContentLabel: string
  retryPlaceholder: string
  fork: string
  forkDesc: string
  forkTitleLabel: string
  forkTitlePlaceholder: string
  forkOptionLabel: string
  forkOptionDirectPath: string
  forkOptionIncludeBranches: string
  forkOptionTargetLevel: string
  apply: string
  actionLoading: string
  actionSuccess: string
  actionError: string
  refreshError: string
  editContentRequired: string
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

type MessageTreeWriteAction = Extract<ConversationTreeMessageWriteActionKind, 'edit' | 'retry' | 'fork'>

const MESSAGE_TREE_WRITE_SOURCE = 'training_message_tree_panel'

function messageTreeWriteActionLabel(action: MessageTreeWriteAction, labels: MessageTreeActionLabels): string {
  if (action === 'retry') return labels.retry
  if (action === 'fork') return labels.fork
  return labels.edit
}

function snapshotFromMessageActionResult(result: MessageActionResult): ConversationTreeBranchSnapshot | null {
  const resultPath = getMessageActionResultPath(result)
  const selectedMessage = result.message ?? resultPath[resultPath.length - 1] ?? null
  if (!selectedMessage && resultPath.length === 0) return null
  return {
    message: selectedMessage,
    path: resultPath.length > 0 ? resultPath : selectedMessage ? [selectedMessage] : [],
    context: [],
    children: result.children,
    searchResults: [],
  }
}

function contextForMessageActionResult(
  baseContext: ConversationTreeMessageActionContext,
  result: MessageActionResult,
): ConversationTreeMessageActionContext | null {
  const resultPath = getMessageActionResultPath(result)
  const selectedMessage = result.message ?? resultPath[resultPath.length - 1]
  if (!selectedMessage) return null

  return buildConversationTreeMessageActionContext({
    provider: baseContext.provider,
    conversationId: result.conversation?.id ?? selectedMessage.conversationId ?? baseContext.conversationId,
    messagePublicId: selectedMessage.publicId,
    branchId: selectedMessage.branchId ?? result.branchId ?? baseContext.branchId,
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

function treeMessageCompactLabel(
  message: ConversationTreeMessage | null | undefined,
  labels: MessageTreeActionLabels,
): string {
  if (!message) return labels.noPath
  return `${treeRoleLabel(message.role, labels)} · ${treeMessagePreview(message)}`
}

function treeMessageTitle(message: ConversationTreeMessage | null | undefined): string | undefined {
  if (!message) return undefined
  return [
    message.publicId,
    message.branchId,
    message.status,
  ].filter(Boolean).join(' · ')
}

function findTreeForkPoint(path: ConversationTreeMessage[]): ConversationTreeMessage | null {
  for (let index = 1; index < path.length; index += 1) {
    const previous = path[index - 1]
    const current = path[index]
    if (!current.branchId || current.branchId === previous.branchId) continue
    return previous
  }
  return null
}

function MessageTreeItem({
  message,
  labels,
  active,
  disabled = false,
  onSelect,
}: {
  message: ConversationTreeMessage
  labels: MessageTreeActionLabels
  active: boolean
  disabled?: boolean
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
      aria-current={active ? 'true' : undefined}
      disabled={disabled}
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
  const [writeExpanded, setWriteExpanded] = React.useState(false)
  const [writeAction, setWriteAction] = React.useState<MessageTreeWriteAction>('edit')
  const [editContent, setEditContent] = React.useState(message.content)
  const [retryContent, setRetryContent] = React.useState('')
  const [forkTitle, setForkTitle] = React.useState('')
  const [forkOption, setForkOption] = React.useState<MessageActionForkOption>('targetLevel')
  const [applyingAction, setApplyingAction] = React.useState<MessageTreeWriteAction | null>(null)
  const [writeError, setWriteError] = React.useState<string | null>(null)
  const [writeStatus, setWriteStatus] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const writePanelId = React.useId()
  const writeFeedbackId = React.useId()
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
    actions: actionsEndpoint,
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
      actions: actionsEndpoint,
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
    actionsEndpoint,
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
    setWriteExpanded(false)
    setWriteAction('edit')
    setEditContent(message.content)
    setRetryContent('')
    setForkTitle('')
    setForkOption('targetLevel')
    setApplyingAction(null)
    setWriteError(null)
    setWriteStatus(null)
  }, [message.content, resetContext, searchQuery])

  React.useEffect(() => () => {
    requestSeqRef.current += 1
  }, [])

  const loadSnapshot = React.useCallback(async (
    nextContext: ConversationTreeMessageActionContext,
    action: 'focus' | 'children' | 'search',
    query: string | null,
    errorLabel = labels.error,
  ): Promise<boolean> => {
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
      if (requestSeqRef.current !== requestSeq) return false
      setFocusedContext(nextContext)
      setSnapshot(nextSnapshot)
      const selection = buildMessageTreeSelection(nextSnapshot, nextContext, message.id)
      if (selection) onSelectPath?.(selection)
      return true
    } catch (err) {
      if (requestSeqRef.current !== requestSeq) return false
      console.error('Failed to load message tree branch data:', err)
      setError(errorLabel)
      return false
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

  const writeActions = React.useMemo(() => {
    const allowed = new Set(focusedContext.availableActions)
    return [
      { action: 'edit' as const, label: labels.edit, description: labels.editDesc, icon: PencilLine },
      { action: 'retry' as const, label: labels.retry, description: labels.retryDesc, icon: RotateCw },
      { action: 'fork' as const, label: labels.fork, description: labels.forkDesc, icon: GitFork },
    ].filter((item) => allowed.has(item.action))
  }, [
    focusedContext.availableActions,
    labels.edit,
    labels.editDesc,
    labels.fork,
    labels.forkDesc,
    labels.retry,
    labels.retryDesc,
  ])

  const handleSubmitWriteAction = React.useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (applyingAction || loadingAction) return

    const nextAction = writeAction
    const nextActionLabel = nextAction === 'retry'
      ? labels.retry
      : nextAction === 'fork'
        ? labels.fork
        : labels.edit
    const nextContent = nextAction === 'edit'
      ? editContent.trim()
      : nextAction === 'retry'
        ? retryContent.trim()
        : null
    if (nextAction === 'edit' && !nextContent) {
      setWriteError(labels.editContentRequired)
      setWriteStatus(null)
      return
    }

    const previousPath = snapshot?.path ?? []
    const previousTailNode = previousPath[previousPath.length - 1] ?? snapshot?.message ?? null
    const previousTailLabel = previousTailNode
      ? treeMessageCompactLabel(previousTailNode, labels)
      : focusedContext.messagePublicId

    setExpanded(true)
    setApplyingAction(nextAction)
    setError(null)
    setWriteError(null)
    setWriteStatus(null)
    try {
      const result = await applyConversationTreeMessageAction(focusedContext, {
        action: nextAction,
        content: nextContent,
        title: nextAction === 'fork' ? forkTitle.trim() : null,
        option: nextAction === 'fork' ? forkOption : null,
        metadata: { source: MESSAGE_TREE_WRITE_SOURCE },
      })
      const resultSnapshot = snapshotFromMessageActionResult(result)
      const nextContext = contextForMessageActionResult(focusedContext, result)
      if (!resultSnapshot || !nextContext) {
        setWriteError(`${nextActionLabel} ${labels.actionError} ${labels.tailNode}: ${previousTailLabel}`)
        return
      }
      setFocusedContext(nextContext)
      setSnapshot(resultSnapshot)
      const selection = buildMessageTreeSelection(resultSnapshot, nextContext, message.id)
      if (selection) onSelectPath?.(selection)
      const resultTail = resultSnapshot.message?.publicId ?? nextContext.messagePublicId
      setWriteStatus([
        `${nextActionLabel} ${labels.actionSuccess}`,
        `${labels.currentPath}: ${labels.pathNodeCount}: ${resultSnapshot.path.length}.`,
        `${labels.branchLabel}: ${nextContext.branchId ?? labels.noBranch}.`,
        `${labels.newTail}: ${resultTail}`,
      ].join(' '))
    } catch (err) {
      console.error('Failed to apply message tree action:', err)
      setWriteError(`${nextActionLabel} ${labels.actionError} ${labels.tailNode}: ${previousTailLabel}`)
    } finally {
      setApplyingAction(null)
    }
  }, [
    applyingAction,
    editContent,
    focusedContext,
    forkOption,
    forkTitle,
    labels.actionError,
    labels.actionSuccess,
    labels.branchLabel,
    labels.currentPath,
    labels.edit,
    labels.editContentRequired,
    labels.fork,
    labels.newTail,
    labels.noBranch,
    labels.pathNodeCount,
    labels.retry,
    labels.tailNode,
    loadingAction,
    message.id,
    onSelectPath,
    retryContent,
    snapshot,
    writeAction,
  ])

  const hasSnapshot = Boolean(snapshot)
  const currentNodeId = snapshot?.message?.publicId ?? focusedContext.messagePublicId
  const isSelectedCurrentNode = selectedTreeNodeId === focusedContext.messagePublicId
    || selectedTreeNodeId === currentNodeId
  const currentPath = snapshot?.path ?? []
  const currentNode = snapshot?.message
    ?? currentPath.find((item) => item.publicId === focusedContext.messagePublicId)
    ?? null
  const currentTailNode = currentPath[currentPath.length - 1] ?? snapshot?.message ?? null
  const currentForkPoint = findTreeForkPoint(currentPath)
  const currentNodeLabel = currentNode ? treeMessageCompactLabel(currentNode, labels) : focusedContext.messagePublicId
  const currentTailLabel = currentTailNode ? treeMessageCompactLabel(currentTailNode, labels) : focusedContext.messagePublicId
  const selectionDescription = isSelectedCurrentNode
    ? labels.selectionCurrent
    : selectedTreeNodeId && selectedPathIds.has(selectedTreeNodeId)
      ? labels.selectionInPath
      : labels.selectionHint
  const selectedTreeNode = currentPath.find((item) => item.publicId === selectedTreeNodeId)
    ?? snapshot?.children.find((item) => item.publicId === selectedTreeNodeId)
    ?? null
  const selectedNodeLabel = selectedTreeNode
    ? treeMessageCompactLabel(selectedTreeNode, labels)
    : selectedTreeNodeId ?? labels.noPath
  const currentPathCountLabel = currentPath.length > 0
    ? `${labels.pathNodeCount}: ${currentPath.length}`
    : labels.noPath
  const currentForkPointLabel = currentForkPoint
    ? treeMessageCompactLabel(currentForkPoint, labels)
    : labels.noForkPoint
  const currentWriteActionLabel = messageTreeWriteActionLabel(writeAction, labels)
  const applyingActionLabel = applyingAction ? messageTreeWriteActionLabel(applyingAction, labels) : null
  const applyingStatus = applyingActionLabel ? `${applyingActionLabel} ${labels.actionLoading}` : null
  const isReadBusy = Boolean(loadingAction)
  const isWriteBusy = Boolean(applyingAction)
  const isTreeBusy = isReadBusy || isWriteBusy
  const editContentMissing = writeAction === 'edit' && editContent.trim().length === 0
  const canSubmitWrite = !isTreeBusy && !editContentMissing
  const submitAccessibleLabel = applyingStatus ?? `${labels.apply}: ${currentWriteActionLabel}`
  const submitDisabledReason = applyingStatus
    ?? (loadingAction ? labels.loading : null)
    ?? (editContentMissing ? labels.editContentRequired : null)
  const shouldShowBranchPanel = expanded && (!loadingAction || hasSnapshot) && (!error || hasSnapshot)

  return (
    <section className="message-tree-actions" aria-label={labels.group} aria-busy={isTreeBusy}>
      <div className="message-tree-actions-header">
        <span className="message-tree-actions-title">
          <ListTree size={14} aria-hidden="true" />
          {labels.title}
        </span>
        <span className="message-tree-badges">
          {isSelectedCurrentNode && <span className="message-tree-selected-badge">{labels.selectedBadge}</span>}
          <span className="message-tree-readonly-badge">{labels.controlledBadge}</span>
        </span>
      </div>
      <p className="message-tree-actions-hint">{labels.hint}</p>
      <div className="message-tree-meta" aria-label={labels.branchLabel}>
        <span className="message-tree-meta-item">
          <span className="message-tree-meta-label">{labels.currentPath}</span>
          <span className="message-tree-meta-value">{currentPathCountLabel}</span>
        </span>
        <span className="message-tree-meta-item">
          <span className="message-tree-meta-label">{labels.branchLabel}</span>
          <span className="message-tree-meta-value">{focusedContext.branchId ?? labels.noBranch}</span>
        </span>
        <span className="message-tree-meta-item">
          <span className="message-tree-meta-label">{labels.currentNode}</span>
          <span className="message-tree-meta-value" title={treeMessageTitle(currentNode) ?? focusedContext.messagePublicId}>
            {currentNodeLabel}
          </span>
        </span>
        <span className="message-tree-meta-item">
          <span className="message-tree-meta-label">{labels.tailNode}</span>
          <span className="message-tree-meta-value" title={treeMessageTitle(currentTailNode) ?? focusedContext.messagePublicId}>
            {currentTailLabel}
          </span>
        </span>
        <span className="message-tree-meta-item">
          <span className="message-tree-meta-label">{labels.forkPoint}</span>
          <span className="message-tree-meta-value" title={treeMessageTitle(currentForkPoint)}>
            {currentForkPointLabel}
          </span>
        </span>
        <span className="message-tree-meta-item">
          <span className="message-tree-meta-label">{labels.searchQueryLabel}</span>
          <span className="message-tree-meta-value">{searchText || searchQuery}</span>
        </span>
      </div>
      <div className="message-tree-selection-context">
        <Route size={13} aria-hidden="true" />
        <span>
          <strong>{labels.currentSelection}</strong>
          <em>
            {selectionDescription}
            {currentPath.length > 0 ? ` ${labels.pathNodeCount}: ${currentPath.length}.` : ''}
          </em>
          <small title={treeMessageTitle(selectedTreeNode) ?? selectedTreeNodeId ?? undefined}>
            {labels.selectedBadge}: {selectedNodeLabel}
          </small>
          <small title={treeMessageTitle(currentTailNode) ?? focusedContext.messagePublicId}>
            {labels.tailNode}: {currentTailLabel}
          </small>
        </span>
      </div>
      <div className="message-tree-action-links">
        <button
          type="button"
          className="message-tree-action"
          title={labels.focusDesc}
          aria-label={loadingAction === 'focus' ? `${labels.focus}: ${labels.loading}` : labels.focus}
          disabled={isTreeBusy}
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
          aria-label={loadingAction === 'children' ? `${labels.children}: ${labels.loading}` : labels.children}
          disabled={isTreeBusy}
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
              disabled={isTreeBusy}
            />
          </label>
          <button
            type="submit"
            title={labels.searchDesc}
            aria-label={loadingAction === 'search' ? `${labels.search}: ${labels.loading}` : labels.search}
            disabled={isTreeBusy}
            onClick={(event) => event.stopPropagation()}
          >
            {loadingAction === 'search' ? <Loader2 size={13} className="spin" /> : <Search size={13} />}
            <span>{labels.search}</span>
          </button>
        </form>
      </div>
      {writeActions.length > 0 && (
        <div className="message-tree-write">
          <button
            type="button"
            className="message-tree-write-toggle"
            aria-expanded={writeExpanded}
            aria-controls={writePanelId}
            disabled={isTreeBusy}
            onClick={(event) => {
              event.stopPropagation()
              setWriteExpanded((value) => !value)
            }}
          >
            <span className="message-tree-write-toggle-title">
              <GitFork size={13} aria-hidden="true" />
              {labels.writesTitle}
            </span>
            <span className="message-tree-write-toggle-copy">
              {writeExpanded ? labels.writesToggleOpen : labels.writesToggle}
              <ChevronDown
                size={13}
                aria-hidden="true"
                className={writeExpanded ? 'expanded' : undefined}
              />
            </span>
          </button>
          {writeExpanded && (
            <form
              id={writePanelId}
              className="message-tree-write-panel"
              onSubmit={handleSubmitWriteAction}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="message-tree-write-tabs" role="tablist" aria-label={labels.writesTitle}>
                {writeActions.map(({ action, label, description, icon: Icon }) => (
                  <button
                    key={action}
                    type="button"
                    className={writeAction === action ? 'active' : undefined}
                    title={description}
                    aria-label={`${label}: ${description}`}
                    aria-pressed={writeAction === action}
                    disabled={isTreeBusy}
                    onClick={() => {
                      setWriteAction(action)
                      setWriteError(null)
                      setWriteStatus(null)
                    }}
                  >
                    <Icon size={13} aria-hidden="true" />
                    <span>{label}</span>
                  </button>
                ))}
              </div>
              <div className="message-tree-write-target">
                <GitFork size={13} aria-hidden="true" />
                <span>
                  <strong>{labels.writeTarget}</strong>
                  <em title={treeMessageTitle(currentNode) ?? focusedContext.messagePublicId}>
                    {currentNodeLabel}
                  </em>
                  <small>{labels.writeTargetDesc}</small>
                  <small title={treeMessageTitle(currentTailNode) ?? focusedContext.messagePublicId}>
                    {labels.tailNode}: {currentTailLabel}
                  </small>
                </span>
              </div>
              {writeAction === 'edit' && (
                <label className="message-tree-write-field">
                  <span>{labels.editContentLabel}</span>
                  <textarea
                    rows={3}
                    value={editContent}
                    placeholder={labels.editPlaceholder}
                    disabled={isTreeBusy}
                    onChange={(event) => {
                      setEditContent(event.target.value)
                      setWriteError(null)
                      setWriteStatus(null)
                    }}
                  />
                </label>
              )}
              {writeAction === 'retry' && (
                <label className="message-tree-write-field">
                  <span>{labels.retryContentLabel}</span>
                  <textarea
                    rows={2}
                    value={retryContent}
                    placeholder={labels.retryPlaceholder}
                    disabled={isTreeBusy}
                    onChange={(event) => {
                      setRetryContent(event.target.value)
                      setWriteError(null)
                      setWriteStatus(null)
                    }}
                  />
                </label>
              )}
              {writeAction === 'fork' && (
                <div className="message-tree-write-grid">
                  <label className="message-tree-write-field">
                    <span>{labels.forkTitleLabel}</span>
                    <input
                      value={forkTitle}
                      placeholder={labels.forkTitlePlaceholder}
                      disabled={isTreeBusy}
                      onChange={(event) => {
                        setForkTitle(event.target.value)
                        setWriteStatus(null)
                      }}
                    />
                  </label>
                  <label className="message-tree-write-field">
                    <span>{labels.forkOptionLabel}</span>
                    <select
                      value={forkOption}
                      disabled={isTreeBusy}
                      onChange={(event) => {
                        setForkOption(event.target.value as MessageActionForkOption)
                        setWriteStatus(null)
                      }}
                    >
                      <option value="targetLevel">{labels.forkOptionTargetLevel}</option>
                      <option value="directPath">{labels.forkOptionDirectPath}</option>
                      <option value="includeBranches">{labels.forkOptionIncludeBranches}</option>
                    </select>
                  </label>
                </div>
              )}
              <div className="message-tree-write-footer">
                <div
                  id={writeFeedbackId}
                  className="message-tree-write-feedback"
                  role={writeError ? 'alert' : 'status'}
                  aria-live={writeError ? 'assertive' : 'polite'}
                >
                  {writeError && <span className="error">{writeError}</span>}
                  {applyingStatus && !writeError && <span className="pending">{applyingStatus}</span>}
                  {writeStatus && !writeError && !applyingStatus && <span className="success">{writeStatus}</span>}
                </div>
                <button
                  type="submit"
                  className="message-tree-write-submit"
                  disabled={!canSubmitWrite}
                  aria-describedby={writeFeedbackId}
                  aria-label={submitDisabledReason ? `${submitAccessibleLabel}: ${submitDisabledReason}` : submitAccessibleLabel}
                >
                  {applyingAction ? <Loader2 size={13} className="spin" /> : <Check size={13} />}
                  <span>{applyingStatus ?? labels.apply}</span>
                </button>
              </div>
            </form>
          )}
        </div>
      )}
      {loadingAction && <div className="message-tree-status" role="status" aria-live="polite">{labels.loading}</div>}
      {error && <div className="message-tree-error" role="alert">{error}</div>}
      {shouldShowBranchPanel && (
        <div className="message-tree-branch-panel">
          <div className="message-tree-section">
            <div className="message-tree-section-title">
              <Route size={13} aria-hidden="true" />
              <span>{labels.currentPath}</span>
              {snapshot?.path.length ? <em>{labels.pathNodeCount}: {snapshot.path.length}</em> : null}
            </div>
            {hasSnapshot && snapshot?.path.length ? (
              <div className="message-tree-path-list">
                {snapshot.path.map((pathMessage) => (
                  <MessageTreeItem
                    key={pathMessage.publicId}
                    message={pathMessage}
                    labels={labels}
                    active={selectedTreeNodeId === pathMessage.publicId || currentNodeId === pathMessage.publicId}
                    disabled={isTreeBusy}
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
                    disabled={isTreeBusy}
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
                    disabled={isTreeBusy}
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
    controlledBadge: t('messageTree.actions.controlledBadge'),
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
    currentNode: t('messageTree.actions.currentNode'),
    tailNode: t('messageTree.actions.tailNode'),
    forkPoint: t('messageTree.actions.forkPoint'),
    noForkPoint: t('messageTree.actions.noForkPoint'),
    currentSelection: t('messageTree.actions.currentSelection'),
    selectionCurrent: t('messageTree.actions.selectionCurrent'),
    selectionInPath: t('messageTree.actions.selectionInPath'),
    selectionHint: t('messageTree.actions.selectionHint'),
    pathNodeCount: t('messageTree.actions.pathNodeCount'),
    writeTarget: t('messageTree.actions.writeTarget'),
    writeTargetDesc: t('messageTree.actions.writeTargetDesc'),
    keptCurrentPath: t('messageTree.actions.keptCurrentPath'),
    newTail: t('messageTree.actions.newTail'),
    roleUser: t('messageTree.actions.roleUser'),
    roleAssistant: t('messageTree.actions.roleAssistant'),
    roleSystem: t('messageTree.actions.roleSystem'),
    statusLabel: t('messageTree.actions.statusLabel'),
    writesTitle: t('messageTree.actions.writesTitle'),
    writesToggle: t('messageTree.actions.writesToggle'),
    writesToggleOpen: t('messageTree.actions.writesToggleOpen'),
    edit: t('messageTree.actions.edit'),
    editDesc: t('messageTree.actions.editDesc'),
    editContentLabel: t('messageTree.actions.editContentLabel'),
    editPlaceholder: t('messageTree.actions.editPlaceholder'),
    retry: t('messageTree.actions.retry'),
    retryDesc: t('messageTree.actions.retryDesc'),
    retryContentLabel: t('messageTree.actions.retryContentLabel'),
    retryPlaceholder: t('messageTree.actions.retryPlaceholder'),
    fork: t('messageTree.actions.fork'),
    forkDesc: t('messageTree.actions.forkDesc'),
    forkTitleLabel: t('messageTree.actions.forkTitleLabel'),
    forkTitlePlaceholder: t('messageTree.actions.forkTitlePlaceholder'),
    forkOptionLabel: t('messageTree.actions.forkOptionLabel'),
    forkOptionDirectPath: t('messageTree.actions.forkOptionDirectPath'),
    forkOptionIncludeBranches: t('messageTree.actions.forkOptionIncludeBranches'),
    forkOptionTargetLevel: t('messageTree.actions.forkOptionTargetLevel'),
    apply: t('messageTree.actions.apply'),
    actionLoading: t('messageTree.actions.actionLoading'),
    actionSuccess: t('messageTree.actions.actionSuccess'),
    actionError: t('messageTree.actions.actionError'),
    refreshError: t('messageTree.actions.refreshError'),
    editContentRequired: t('messageTree.actions.editContentRequired'),
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
                    <Avatar name={persona?.name || msg.sender_id} color={borderColor || '#0F766E'} size={28} />
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
                  <Avatar name={persona?.name || personaId} color={borderColor || '#0F766E'} size={28} />
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
