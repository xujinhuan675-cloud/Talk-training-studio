import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchAnnouncementFeed,
  isAnnouncementRead,
  isNoticeRead,
  loadAnnouncementReadState,
  markAnnouncementFeedRead,
  persistAnnouncementReadState,
  UNAVAILABLE_ANNOUNCEMENT_FEED,
  unreadAnnouncementCount,
  type AnnouncementFeed,
  type AnnouncementItem,
  type AnnouncementReadState,
} from '../services/announcements'

export function useAnnouncements() {
  const [feed, setFeed] = useState<AnnouncementFeed>(UNAVAILABLE_ANNOUNCEMENT_FEED)
  const [readState, setReadState] = useState<AnnouncementReadState>(loadAnnouncementReadState)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    const nextFeed = await fetchAnnouncementFeed()
    setFeed(nextFeed)
    setLoading(false)
    return nextFeed
  }, [])

  useEffect(() => {
    let active = true
    void fetchAnnouncementFeed().then((nextFeed) => {
      if (!active) return
      setFeed(nextFeed)
      setLoading(false)
    })
    return () => {
      active = false
    }
  }, [])

  const markVisibleAsRead = useCallback(() => {
    setReadState((current) => {
      const next = markAnnouncementFeedRead(current, feed)
      persistAnnouncementReadState(next)
      return next
    })
  }, [feed])

  return {
    feed,
    loading,
    refresh,
    unreadCount: useMemo(() => unreadAnnouncementCount(readState, feed), [feed, readState]),
    markVisibleAsRead,
    isNoticeRead: (notice: string | null) => isNoticeRead(readState, notice),
    isAnnouncementRead: (item: AnnouncementItem) => isAnnouncementRead(readState, item),
  }
}
