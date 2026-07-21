import React from 'react'
import { Languages, Monitor, Moon, Sun } from 'lucide-react'
import { useTheme, type ThemePreference } from '../../contexts/ThemeContext'
import { SUPPORTED_LOCALES, useI18n, type Locale } from '../../i18n'
import { Button } from '../ui/button'
import { Select } from '../ui/form'
import { SegmentedControl, type SegmentedControlOption } from '../ui/segmented-control'
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
  const themeOptions: SegmentedControlOption<ThemePreference>[] = themeItems.map(({ value, label, Icon }) => ({
    value,
    title: `${themeControlLabel}: ${label}`,
    label: (
      <>
        <Icon className="topbar-theme-icon" size={15} aria-hidden="true" />
        <span>{label}</span>
      </>
    ),
  }))
  const languageLabel = t('app.languageLabel')

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
        <SegmentedControl
          className="topbar-theme-control"
          ariaLabel={`${themeControlLabel}. ${resolvedThemeLabel}`}
          data-theme-mode={mode}
          data-resolved-theme={theme}
          onValueChange={setMode}
          options={themeOptions}
          size="sm"
          value={mode}
        />
        <label className="topbar-language" aria-label={languageLabel} title={languageLabel}>
          <Languages size={15} />
          <Select
            className="topbar-language-select"
            value={locale}
            onChange={(event) => setLocale(event.target.value as Locale)}
            aria-label={languageLabel}
          >
            {SUPPORTED_LOCALES.map((item) => (
              <option key={item.value} value={item.value}>
                {t(item.labelKey)}
              </option>
            ))}
          </Select>
        </label>
        <UserMenu />
      </div>
    </header>
  )
}

export default TopBar
