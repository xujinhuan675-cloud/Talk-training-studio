import React from 'react'
import { Flame, Languages, Star } from 'lucide-react'
import { SUPPORTED_LOCALES, useI18n, type Locale } from '../../i18n'
import './TopBar.css'

const LogoSvg: React.FC<{ size?: number }> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="#2D9C6F" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M2 17l10 5 10-5" stroke="#2D9C6F" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M2 12l10 5 10-5" stroke="#2D9C6F" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

interface TopBarProps {
  onSearchClick?: () => void
}

const TopBar: React.FC<TopBarProps> = ({ onSearchClick }) => {
  const { locale, setLocale, t } = useI18n()

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-logo">
          <LogoSvg size={22} />
          <span className="topbar-wordmark">DaBoss</span>
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
      </div>
      <div className="topbar-right">
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
        <div className="topbar-stat">
          <Flame size={16} />
          <span>7</span>
        </div>
        <div className="topbar-stat">
          <Star size={16} />
          <span>1280</span>
        </div>
        <div className="topbar-level-pill">{t('app.levelTitle')}</div>
        <div className="topbar-avatar">{t('app.avatarInitial')}</div>
      </div>
    </header>
  )
}

export default TopBar
