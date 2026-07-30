/**
 * Read-only announcement client adapted from
 * outside-project/new-api-main/web/src/hooks/use-notifications.ts.
 * TalkWise keeps only browser-local read state; it never writes upstream.
 */

export type AnnouncementFeedState = 'available' | 'unavailable'

export interface AnnouncementItem {
  id: string
  content: string
  extra: string | null
  publishedAt: string | null
  type: 'default' | 'ongoing' | 'success' | 'warning' | 'error'
}

export interface AnnouncementFeed {
  state: AnnouncementFeedState
  notice: string | null
  announcements: AnnouncementItem[]
}

export interface AnnouncementReadState {
  noticeSignature: string | null
  announcementKeys: string[]
}

const READ_STATE_STORAGE_KEY = 'talkwise.announcements.read.v1'
const MAX_READ_ANNOUNCEMENTS = 200
const ALLOWED_TYPES = new Set<AnnouncementItem['type']>([
  'default',
  'ongoing',
  'success',
  'warning',
  'error',
])

export const UNAVAILABLE_ANNOUNCEMENT_FEED: AnnouncementFeed = {
  state: 'unavailable',
  notice: null,
  announcements: [],
}

function recordOf(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function textOf(value: unknown, maxLength: number): string | null {
  if (typeof value !== 'string') return null
  const normalized = value.trim().slice(0, maxLength)
  return normalized || null
}

function hashText(value: string): string {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index)
    hash |= 0
  }
  return hash.toString(36)
}

function normalizeAnnouncement(value: unknown): AnnouncementItem | null {
  const item = recordOf(value)
  if (!item) return null
  const content = textOf(item.content, 2_000)
  if (!content) return null
  const rawId = item.id
  const id = typeof rawId === 'string' || typeof rawId === 'number'
    ? String(rawId).trim().slice(0, 80)
    : ''
  const extra = textOf(item.extra, 500)
  const publishedAt = textOf(item.published_at, 120)
  const rawType = textOf(item.type, 24)
  const type = rawType && ALLOWED_TYPES.has(rawType as AnnouncementItem['type'])
    ? rawType as AnnouncementItem['type']
    : 'default'
  const fallbackId = hashText([content, extra ?? '', publishedAt ?? '', type].join('\u001f'))

  return {
    id: id || `hash:${fallbackId}`,
    content,
    extra,
    publishedAt,
    type,
  }
}

export function normalizeAnnouncementFeed(payload: unknown): AnnouncementFeed {
  const envelope = recordOf(payload)
  const data = recordOf(envelope?.data)
  if (!data || data.state !== 'available') return UNAVAILABLE_ANNOUNCEMENT_FEED

  const rawAnnouncements = Array.isArray(data.announcements) ? data.announcements : []
  return {
    state: 'available',
    notice: textOf(data.notice, 8_000),
    announcements: rawAnnouncements
      .map(normalizeAnnouncement)
      .filter((item): item is AnnouncementItem => Boolean(item)),
  }
}

export async function fetchAnnouncementFeed(
  fetcher: typeof fetch = fetch,
): Promise<AnnouncementFeed> {
  try {
    const response = await fetcher('/api/v1/announcements', {
      method: 'GET',
      credentials: 'same-origin',
    })
    if (!response.ok) return UNAVAILABLE_ANNOUNCEMENT_FEED
    return normalizeAnnouncementFeed(await response.json())
  } catch {
    return UNAVAILABLE_ANNOUNCEMENT_FEED
  }
}

function getStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage ?? null
  } catch {
    return null
  }
}

function normalizeReadState(value: unknown): AnnouncementReadState {
  const data = recordOf(value)
  const noticeSignature = textOf(data?.noticeSignature, 80)
  const announcementKeys = Array.isArray(data?.announcementKeys)
    ? data.announcementKeys
      .map((key) => textOf(key, 120))
      .filter((key): key is string => Boolean(key))
      .slice(-MAX_READ_ANNOUNCEMENTS)
    : []
  return { noticeSignature, announcementKeys: [...new Set(announcementKeys)] }
}

export function loadAnnouncementReadState(): AnnouncementReadState {
  const storage = getStorage()
  if (!storage) return { noticeSignature: null, announcementKeys: [] }
  try {
    const raw = storage.getItem(READ_STATE_STORAGE_KEY)
    return raw ? normalizeReadState(JSON.parse(raw)) : { noticeSignature: null, announcementKeys: [] }
  } catch {
    return { noticeSignature: null, announcementKeys: [] }
  }
}

export function persistAnnouncementReadState(state: AnnouncementReadState): void {
  const storage = getStorage()
  if (!storage) return
  try {
    storage.setItem(READ_STATE_STORAGE_KEY, JSON.stringify(normalizeReadState(state)))
  } catch {
    // Persisting read state is intentionally best-effort.
  }
}

export function announcementKey(item: AnnouncementItem): string {
  return `id:${item.id}`
}

export function noticeSignature(notice: string): string {
  return hashText(notice)
}

export function isNoticeRead(readState: AnnouncementReadState, notice: string | null): boolean {
  return !notice || readState.noticeSignature === noticeSignature(notice)
}

export function isAnnouncementRead(readState: AnnouncementReadState, item: AnnouncementItem): boolean {
  return readState.announcementKeys.includes(announcementKey(item))
}

export function markAnnouncementFeedRead(
  readState: AnnouncementReadState,
  feed: AnnouncementFeed,
): AnnouncementReadState {
  if (feed.state !== 'available') return readState
  const nextState: AnnouncementReadState = {
    noticeSignature: feed.notice ? noticeSignature(feed.notice) : readState.noticeSignature,
    announcementKeys: [
      ...readState.announcementKeys,
      ...feed.announcements.map(announcementKey),
    ],
  }
  return normalizeReadState(nextState)
}

export function unreadAnnouncementCount(readState: AnnouncementReadState, feed: AnnouncementFeed): number {
  if (feed.state !== 'available') return 0
  const unreadNotice = isNoticeRead(readState, feed.notice) ? 0 : 1
  return unreadNotice + feed.announcements.filter((item) => !isAnnouncementRead(readState, item)).length
}
