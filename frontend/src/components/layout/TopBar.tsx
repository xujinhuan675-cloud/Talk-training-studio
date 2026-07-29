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
  Search,
  Sun,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuthContext } from '../../contexts/AuthContext'
import { useTheme, type ThemePreference } from '../../contexts/ThemeContext'
import { SUPPORTED_LOCALES, useI18n, type Locale } from '../../i18n'
import { NEWAPI_USAGE_URL } from '../../services/auth'
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
        <Link className="topbar-logo" to="/" aria-label="TalkWise">
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

        <DropdownMenu>
          <Button asChild className="topbar-icon-trigger" variant="secondary" size="icon">
            <DropdownMenuTrigger
              aria-label={tr('公告', 'Announcements')}
              title={tr('公告', 'Announcements')}
            >
              <Bell size={16} aria-hidden="true" />
            </DropdownMenuTrigger>
          </Button>

          <DropdownMenuContent className="topbar-notice-menu" align="end">
            <DropdownMenuLabel className="topbar-quick-menu-heading">{tr('公告', 'Announcements')}</DropdownMenuLabel>
            <div className="topbar-notice-card">
              <span className="topbar-notice-dot" aria-hidden="true" />
              <span className="topbar-notice-copy">
                <strong>{tr('公告中心', 'Announcements')}</strong>
                <span>{tr('账号、公告和系统状态会在这里展示', 'Account, notices, and status appear here')}</span>
              </span>
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
