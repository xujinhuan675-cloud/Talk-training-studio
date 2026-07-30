import React from 'react'
import {
  Bell,
  Check,
  CreditCard,
  Languages,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  Sun,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { APP_ROUTES } from '../../appRoutes'
import { useAuthContext } from '../../contexts/AuthContext'
import { useTheme, type ThemePreference } from '../../contexts/ThemeContext'
import { useAnnouncements } from '../../hooks/useAnnouncements'
import { SUPPORTED_LOCALES, useI18n, type Locale } from '../../i18n'
import { NEWAPI_USAGE_URL } from '../../services/auth'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import UserMenu from './UserMenu'
import './TopBar.css'

const TALKWISE_ICON_SRC = '/talkwise-icon.svg'

function formatQuota(value: number | null | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return new Intl.NumberFormat(undefined, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function announcementDotColor(type: string, read: boolean): string {
  if (read) return 'var(--text-muted)'
  if (type === 'warning') return 'var(--warning)'
  if (type === 'error') return 'var(--danger)'
  if (type === 'success') return 'var(--success)'
  return 'var(--primary)'
}

function formatAnnouncementDate(value: string | null): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

interface TopBarProps {
  navCollapsed?: boolean
  onNavToggle?: () => void
  onSearchClick?: () => void
}

const TopBar: React.FC<TopBarProps> = ({ navCollapsed = false, onNavToggle, onSearchClick }) => {
  const { locale, setLocale, t, tr } = useI18n()
  const { currentUser } = useAuthContext()
  const { mode, setMode, theme } = useTheme()
  const themeControlLabel = t('app.theme.mode')
  const resolvedThemeLabel = theme === 'dark'
    ? t('app.theme.currentDark')
    : t('app.theme.currentLight')
  const themeItems: { value: ThemePreference; label: string; Icon: typeof Sun }[] = [
    { value: 'light', label: t('app.theme.light'), Icon: Sun },
    { value: 'dark', label: t('app.theme.dark'), Icon: Moon },
    { value: 'system', label: t('app.theme.system'), Icon: Monitor },
  ]
  const languageLabel = t('app.languageLabel')
  const currentLocaleLabel = t(SUPPORTED_LOCALES.find((item) => item.value === locale)?.labelKey ?? 'language.zh')
  const ActiveThemeIcon = themeItems.find((item) => item.value === mode)?.Icon ?? Sun
  const quotaText = formatQuota(currentUser?.quotaRemaining)
  const {
    feed: announcementFeed,
    loading: announcementsLoading,
    refresh: refreshAnnouncements,
    unreadCount,
    markVisibleAsRead,
    isNoticeRead,
    isAnnouncementRead,
  } = useAnnouncements()
  const handleAnnouncementsOpenChange = (open: boolean) => {
    if (!open) return
    markVisibleAsRead()
    void refreshAnnouncements()
  }
  const quotaLabel = quotaText
    ? tr('余额 {count}', 'Balance {count}', { count: quotaText })
    : tr('账户', 'Account')

  return (
    <header className="topbar">
      <div className="topbar-left">
        <Button
          className="topbar-sidebar-toggle"
          variant="ghost"
          size="icon"
          type="button"
          aria-label={navCollapsed ? tr('展开侧边栏', 'Expand sidebar') : tr('收起侧边栏', 'Collapse sidebar')}
          title={navCollapsed ? tr('展开侧边栏', 'Expand sidebar') : tr('收起侧边栏', 'Collapse sidebar')}
          aria-expanded={!navCollapsed}
          onClick={onNavToggle}
        >
          {navCollapsed ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
        </Button>
        <Link className="topbar-logo" to={APP_ROUTES.workbench} aria-label="TalkWise">
          <img className="topbar-logo-mark" src={TALKWISE_ICON_SRC} alt="" aria-hidden="true" />
          <span className="topbar-wordmark">TalkWise</span>
        </Link>
      </div>
      <Button
        className="topbar-search"
        variant="ghost"
        onClick={onSearchClick}
        aria-label={t('app.searchPlaceholder')}
      >
        <Search className="topbar-search-icon" size={15} aria-hidden="true" />
        <span className="topbar-search-text">{t('app.searchPlaceholder')}</span>
        <kbd className="topbar-search-kbd">&#8984;K</kbd>
      </Button>
      <div className="topbar-right">
        <a
          className="topbar-account-chip"
          href={NEWAPI_USAGE_URL}
          target="_blank"
          rel="noreferrer"
          aria-label={quotaLabel}
          title={quotaLabel}
        >
          <CreditCard size={14} aria-hidden="true" />
          <span>{quotaLabel}</span>
        </a>

        <DropdownMenu onOpenChange={handleAnnouncementsOpenChange}>
          <Button asChild className="topbar-icon-trigger" variant="secondary" size="icon">
            <DropdownMenuTrigger
              aria-label={tr('公告', 'Announcements')}
              title={tr('公告', 'Announcements')}
              style={{ position: 'relative' }}
            >
              <Bell size={16} aria-hidden="true" />
              {unreadCount > 0 ? (
                <Badge
                  tone="danger"
                  aria-label={tr('{count} 条未读公告', '{count} unread announcements', { count: unreadCount })}
                  style={{
                    position: 'absolute',
                    top: -7,
                    right: -7,
                    minWidth: 18,
                    minHeight: 18,
                    padding: '0 4px',
                    fontSize: 10,
                    lineHeight: '18px',
                    textAlign: 'center',
                    pointerEvents: 'none',
                  }}
                >
                  {unreadCount > 99 ? '99+' : unreadCount}
                </Badge>
              ) : null}
            </DropdownMenuTrigger>
          </Button>

          <DropdownMenuContent className="topbar-notice-menu" align="end">
            <div className="topbar-notice-list" aria-live="polite">
              <strong className="topbar-notice-heading">{tr('公告', 'Announcements')}</strong>
              {announcementsLoading ? (
                <div className="topbar-notice-card" role="status">
                  <span className="topbar-notice-dot" aria-hidden="true" />
                  <span className="topbar-notice-copy">
                    <strong>{tr('正在加载公告...', 'Loading announcements...')}</strong>
                    <span>{tr('请稍候', 'Please wait')}</span>
                  </span>
                </div>
              ) : announcementFeed.state === 'unavailable' ? (
                <div className="topbar-notice-card" role="status">
                  <span className="topbar-notice-dot" style={{ background: 'var(--warning)' }} aria-hidden="true" />
                  <span className="topbar-notice-copy">
                    <strong>{tr('公告暂时无法获取', 'Announcements are temporarily unavailable')}</strong>
                    <span>{tr('请稍后重试', 'Try again shortly')}</span>
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={tr('重新加载公告', 'Reload announcements')}
                    title={tr('重新加载公告', 'Reload announcements')}
                    onClick={() => { void refreshAnnouncements() }}
                  >
                    <RefreshCw size={15} aria-hidden="true" />
                  </Button>
                </div>
              ) : !announcementFeed.notice && announcementFeed.announcements.length === 0 ? (
                <div className="topbar-notice-card" role="status">
                  <span className="topbar-notice-dot" style={{ background: 'var(--text-muted)' }} aria-hidden="true" />
                  <span className="topbar-notice-copy">
                    <strong>{tr('暂无公告', 'No announcements')}</strong>
                    <span>{tr('最新通知会显示在这里', 'Latest notices will appear here')}</span>
                  </span>
                </div>
              ) : (
                <>
                  {announcementFeed.notice ? (() => {
                    const read = isNoticeRead(announcementFeed.notice)
                    return (
                      <div className="topbar-notice-card" aria-label={read ? tr('通知，已读', 'Notice, read') : tr('通知，未读', 'Notice, unread')}>
                        <span className="topbar-notice-dot" style={{ background: announcementDotColor('default', read) }} aria-hidden="true" />
                        <span className="topbar-notice-copy">
                          <strong>{tr('通知', 'Notice')}</strong>
                          <span style={{ whiteSpace: 'pre-wrap' }}>{announcementFeed.notice}</span>
                          <span>{read ? tr('已读', 'Read') : tr('未读', 'Unread')}</span>
                        </span>
                      </div>
                    )
                  })() : null}
                  {announcementFeed.announcements.map((item) => {
                    const read = isAnnouncementRead(item)
                    const publishedAt = formatAnnouncementDate(item.publishedAt)
                    return (
                      <div key={item.id} className="topbar-notice-card" aria-label={read ? tr('系统公告，已读', 'System announcement, read') : tr('系统公告，未读', 'System announcement, unread')}>
                        <span className="topbar-notice-dot" style={{ background: announcementDotColor(item.type, read) }} aria-hidden="true" />
                        <span className="topbar-notice-copy">
                          <strong>{tr('系统公告', 'System announcement')}</strong>
                          <span style={{ whiteSpace: 'pre-wrap' }}>{item.content}</span>
                          {item.extra ? <span style={{ whiteSpace: 'pre-wrap' }}>{item.extra}</span> : null}
                          <span>{[publishedAt, read ? tr('已读', 'Read') : tr('未读', 'Unread')].filter(Boolean).join(' · ')}</span>
                        </span>
                      </div>
                    )
                  })}
                </>
              )}
            </div>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <Button asChild className="topbar-icon-trigger" variant="secondary" size="icon">
            <DropdownMenuTrigger
              aria-label={`${themeControlLabel}. ${resolvedThemeLabel}`}
              title={`${themeControlLabel}: ${resolvedThemeLabel}`}
            >
              <ActiveThemeIcon size={16} aria-hidden="true" />
            </DropdownMenuTrigger>
          </Button>

          <DropdownMenuContent className="topbar-quick-menu" align="end">
            <DropdownMenuLabel className="topbar-quick-menu-heading">{themeControlLabel}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              className="topbar-quick-menu-group"
              value={mode}
              onValueChange={(value) => setMode(value as ThemePreference)}
              aria-label={`${themeControlLabel}. ${resolvedThemeLabel}`}
            >
              {themeItems.map(({ value, label, Icon }) => {
                const selected = mode === value
                return (
                  <DropdownMenuRadioItem
                    key={value}
                    value={value}
                    className={`topbar-quick-menu-item${selected ? ' selected' : ''}`}
                  >
                    <Icon className="topbar-quick-menu-item-icon" size={15} aria-hidden="true" />
                    <span>{label}</span>
                    {selected ? <Check className="topbar-quick-menu-check" size={15} aria-hidden="true" /> : null}
                  </DropdownMenuRadioItem>
                )
              })}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <Button asChild className="topbar-icon-trigger" variant="secondary" size="icon">
            <DropdownMenuTrigger
              aria-label={`${languageLabel}: ${currentLocaleLabel}`}
              title={`${languageLabel}: ${currentLocaleLabel}`}
            >
              <Languages size={16} aria-hidden="true" />
            </DropdownMenuTrigger>
          </Button>

          <DropdownMenuContent className="topbar-quick-menu topbar-language-menu" align="end">
            <DropdownMenuLabel className="topbar-quick-menu-heading">{languageLabel}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              className="topbar-quick-menu-group"
              value={locale}
              onValueChange={(value) => setLocale(value as Locale)}
              aria-label={languageLabel}
            >
              {SUPPORTED_LOCALES.map((item) => {
                const selected = locale === item.value
                return (
                  <DropdownMenuRadioItem
                    key={item.value}
                    value={item.value}
                    className={`topbar-quick-menu-item${selected ? ' selected' : ''}`}
                  >
                    <Languages className="topbar-quick-menu-item-icon" size={15} aria-hidden="true" />
                    <span>{t(item.labelKey)}</span>
                    {selected ? <Check className="topbar-quick-menu-check" size={15} aria-hidden="true" /> : null}
                  </DropdownMenuRadioItem>
                )
              })}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <UserMenu />
      </div>
    </header>
  )
}

export default TopBar
