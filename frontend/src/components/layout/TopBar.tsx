import React from 'react'
import { Check, Languages, Monitor, Moon, Sun } from 'lucide-react'
import { useTheme, type ThemePreference } from '../../contexts/ThemeContext'
import { SUPPORTED_LOCALES, useI18n, type Locale } from '../../i18n'
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

interface TopBarProps {
  onSearchClick?: () => void
}

const TopBar: React.FC<TopBarProps> = ({ onSearchClick }) => {
  const { locale, setLocale, t } = useI18n()
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

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-logo">
          <img className="topbar-logo-mark" src={TALKWISE_ICON_SRC} alt="" aria-hidden="true" />
          <span className="topbar-wordmark">TalkWise</span>
        </div>
      </div>
      <Button
        className="topbar-search"
        variant="ghost"
        onClick={onSearchClick}
        aria-label={t('app.searchPlaceholder')}
      >
        <span className="topbar-search-text">{t('app.searchPlaceholder')}</span>
        <kbd className="topbar-search-kbd">&#8984;K</kbd>
      </Button>
      <div className="topbar-right">
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
