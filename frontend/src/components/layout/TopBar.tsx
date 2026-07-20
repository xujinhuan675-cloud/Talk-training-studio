import React from 'react'
import { Languages, Monitor, Moon, Sun } from 'lucide-react'
import { useTheme, type ThemePreference } from '../../contexts/ThemeContext'
import { SUPPORTED_LOCALES, useI18n, type Locale } from '../../i18n'
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
  const themeOptions: { mode: ThemePreference; label: string; Icon: typeof Sun }[] = [
    { mode: 'light', label: t('app.theme.light'), Icon: Sun },
    { mode: 'dark', label: t('app.theme.dark'), Icon: Moon },
    { mode: 'system', label: t('app.theme.system'), Icon: Monitor },
  ]

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-logo">
          <img className="topbar-logo-mark" src={TALKWISE_ICON_SRC} alt="" aria-hidden="true" />
          <span className="topbar-wordmark">TalkWise</span>
        </div>
      </div>
      <div
        className="topbar-search"
        role="button"
        tabIndex={0}
        onClick={onSearchClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onSearchClick?.()
          }
        }}
      >
        <span className="topbar-search-text">{t('app.searchPlaceholder')}</span>
        <kbd className="topbar-search-kbd">&#8984;K</kbd>
      </div>
      <div className="topbar-right">
        <div
          className="topbar-theme-control"
          role="group"
          aria-label={`${themeControlLabel}. ${resolvedThemeLabel}`}
          data-theme-mode={mode}
          data-resolved-theme={theme}
        >
          {themeOptions.map(({ mode: optionMode, label, Icon }) => (
            <button
              key={optionMode}
              className="topbar-theme-option"
              type="button"
              onClick={() => setMode(optionMode)}
              aria-pressed={mode === optionMode}
              title={`${themeControlLabel}: ${label}`}
            >
              <Icon size={15} />
              <span>{label}</span>
            </button>
          ))}
        </div>
        <label className="topbar-language" aria-label={t('app.languageLabel')} title={t('app.languageLabel')}>
          <Languages size={15} />
          <select value={locale} onChange={(event) => setLocale(event.target.value as Locale)}>
            {SUPPORTED_LOCALES.map((item) => (
              <option key={item.value} value={item.value}>
                {t(item.labelKey)}
              </option>
            ))}
          </select>
        </label>
        <UserMenu />
      </div>
    </header>
  )
}

export default TopBar
