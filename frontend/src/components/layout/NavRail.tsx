import React, { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Dumbbell, MessageSquare, PanelLeftClose, PanelLeftOpen, Settings, Swords, TrendingUp } from 'lucide-react'
import { useI18n, type TranslationKey } from '../../i18n'
import './NavRail.css'

const TALKWISE_ICON_SRC = '/talkwise-icon.svg'
const STORAGE_KEY = 'talkwise.navrail.collapsed'

interface NavItem {
  to: string
  icon: React.ReactNode
  labelKey: TranslationKey
}

const navItems: NavItem[] = [
  { to: '/training-studio', icon: <Dumbbell size={18} />, labelKey: 'nav.trainingStudio' },
  { to: '/chat', icon: <MessageSquare size={18} />, labelKey: 'nav.chat' },
  { to: '/battle-prep', icon: <Swords size={18} />, labelKey: 'nav.battlePrep' },
  { to: '/growth', icon: <TrendingUp size={18} />, labelKey: 'nav.growth' },
  { to: '/settings', icon: <Settings size={18} />, labelKey: 'nav.settings' },
]

const NavRail: React.FC = () => {
  const location = useLocation()
  const { t, tr } = useI18n()
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(STORAGE_KEY) === 'true'
  })

  const isActive = (path: string) => location.pathname.startsWith(path)

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, String(collapsed))
  }, [collapsed])

  const toggleLabel = collapsed ? tr('展开侧边栏', 'Expand sidebar') : tr('收起侧边栏', 'Collapse sidebar')

  return (
    <nav className={`navrail${collapsed ? ' navrail--collapsed' : ''}`} aria-label={tr('主导航', 'Primary navigation')}>
      <div className="navrail-header">
        <Link to="/" className="navrail-logo" aria-label={t('nav.home')} title={collapsed ? 'TalkWise' : undefined}>
          <img className="navrail-logo-mark" src={TALKWISE_ICON_SRC} alt="" aria-hidden="true" />
          <span className="navrail-wordmark">TalkWise</span>
        </Link>
        <button
          type="button"
          className="navrail-toggle"
          aria-label={toggleLabel}
          title={toggleLabel}
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
        </button>
      </div>
      <div className="navrail-items">
        {navItems.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className={`navrail-link${isActive(item.to) ? ' active' : ''}`}
            title={t(item.labelKey)}
            aria-label={t(item.labelKey)}
          >
            <span className="navrail-link-icon" aria-hidden="true">
              {item.icon}
            </span>
            <span className="navrail-link-label">{t(item.labelKey)}</span>
          </Link>
        ))}
      </div>
    </nav>
  )
}

export default NavRail
