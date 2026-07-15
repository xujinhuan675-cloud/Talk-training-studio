import React, { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  ChevronsLeft,
  ChevronsRight,
  ClipboardList,
  Dumbbell,
  Home,
  MessageSquare,
  Settings,
  Swords,
  TrendingUp,
} from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { useI18n, type TranslationKey } from '../../i18n'
import { type SystemRole } from '../../services/auth'
import './NavRail.css'

const STORAGE_KEY = 'talkwise.navrail.collapsed'

interface NavItem {
  to: string
  icon: React.ReactNode
  labelKey: TranslationKey
  exact?: boolean
  roles?: SystemRole[]
}

const navItems: NavItem[] = [
  { to: '/', icon: <Home size={18} />, labelKey: 'nav.home', exact: true },
  { to: '/scenario-training', icon: <ClipboardList size={18} />, labelKey: 'nav.scenarioTraining' },
  { to: '/training-studio', icon: <Dumbbell size={18} />, labelKey: 'nav.trainingStudio' },
  { to: '/chat', icon: <MessageSquare size={18} />, labelKey: 'nav.chat' },
  { to: '/battle-prep', icon: <Swords size={18} />, labelKey: 'nav.battlePrep', roles: ['admin'] },
  { to: '/growth', icon: <TrendingUp size={18} />, labelKey: 'nav.growth' },
  { to: '/settings', icon: <Settings size={18} />, labelKey: 'nav.settings', roles: ['admin'] },
]

const NavRail: React.FC = () => {
  const location = useLocation()
  const { t, tr } = useI18n()
  const { currentUser } = useAuthContext()
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(STORAGE_KEY) === 'true'
  })

  const visibleNavItems = navItems.filter((item) => {
    if (!item.roles) return true
    if (!currentUser) return false
    return currentUser.systemRole ? item.roles.includes(currentUser.systemRole) : false
  })

  const isActive = (item: NavItem) => {
    if (item.exact) return location.pathname === item.to
    return location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)
  }

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, String(collapsed))
  }, [collapsed])

  const toggleLabel = collapsed ? tr('展开侧边栏', 'Expand sidebar') : tr('收起侧边栏', 'Collapse sidebar')
  const toggleText = collapsed ? tr('展开', 'Expand') : tr('收起', 'Collapse')
  return (
    <nav className={`navrail${collapsed ? ' navrail--collapsed' : ''}`} aria-label={tr('主导航', 'Primary navigation')}>
      <div className="navrail-items">
        {visibleNavItems.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className={`navrail-link${isActive(item) ? ' active' : ''}`}
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
      <div className="navrail-footer">
        <button
          type="button"
          className="navrail-toggle"
          aria-label={toggleLabel}
          title={toggleLabel}
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((value) => !value)}
        >
          <span className="navrail-toggle-icon" aria-hidden="true">
            {collapsed ? <ChevronsRight size={19} /> : <ChevronsLeft size={19} />}
          </span>
          <span className="navrail-toggle-label">{toggleText}</span>
        </button>
      </div>
    </nav>
  )
}

export default NavRail
