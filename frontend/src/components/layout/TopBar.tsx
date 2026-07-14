import React from 'react'
import { Link } from 'react-router-dom'
import { Flame, Languages, Star } from 'lucide-react'
import { SUPPORTED_LOCALES, useI18n, type Locale } from '../../i18n'
import { useGrowth } from '../../hooks/useGrowth'
import './TopBar.css'

const TALKWISE_ICON_SRC = '/talkwise-icon.svg'

interface TopBarProps {
  onSearchClick?: () => void
}

function formatCompactNumber(value: number): string {
  if (value >= 10000) return `${Math.floor(value / 1000) / 10}k`
  return String(value)
}

function getLevelTitle(level: number, tr: ReturnType<typeof useI18n>['tr']): string {
  if (level <= 1) return tr('沟通新手', 'New Communicator')
  if (level <= 3) return tr('沟通练习者', 'Communication Trainee')
  if (level <= 5) return tr('沟通达人', 'Skilled Communicator')
  if (level <= 7) return tr('沟通专家', 'Communication Expert')
  return tr('沟通大师', 'Communication Master')
}

const TopBar: React.FC<TopBarProps> = ({ onSearchClick }) => {
  const { locale, setLocale, t, tr } = useI18n()
  const { loading, error, xp, levelInfo, streak } = useGrowth()
  const statsUnavailable = loading || Boolean(error)
  const levelTitle = getLevelTitle(levelInfo.level, tr)
  const streakText = statsUnavailable ? '--' : String(streak)
  const xpText = statsUnavailable ? '--' : formatCompactNumber(xp)
  const levelText = statsUnavailable
    ? 'Lv.--'
    : tr('Lv.{level} {title}', 'Lv.{level} {title}', { level: levelInfo.level, title: levelTitle })
  const levelLabel = loading
    ? tr('成长数据加载中', 'Loading growth')
    : error
      ? tr('成长数据暂不可用', 'Growth unavailable')
      : tr('当前等级 Lv.{level} {title}', 'Current level: Lv.{level} {title}', {
        level: levelInfo.level,
        title: levelTitle,
      })
  const streakLabel = statsUnavailable
    ? tr('连续练习天数加载中', 'Practice streak loading')
    : tr('连续练习 {count} 天', '{count} day streak', { count: streak })
  const xpLabel = statsUnavailable
    ? tr('总经验值加载中', 'Total XP loading')
    : tr('总经验值 {count}', '{count} total XP', { count: xp })

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
        <Link
          to="/growth"
          className="topbar-stat"
          aria-label={streakLabel}
          title={tr('连续练习天数', 'Practice streak')}
        >
          <Flame size={16} />
          <span>{streakText}</span>
        </Link>
        <Link
          to="/growth"
          className="topbar-stat"
          aria-label={xpLabel}
          title={tr('总经验值', 'Total XP')}
        >
          <Star size={16} />
          <span>{xpText}</span>
        </Link>
        <Link
          to="/growth"
          className="topbar-level-pill"
          aria-label={levelLabel}
          title={tr('查看成长统计', 'View growth stats')}
        >
          {levelText}
        </Link>
        <div className="topbar-avatar">{t('app.avatarInitial')}</div>
      </div>
    </header>
  )
}

export default TopBar
