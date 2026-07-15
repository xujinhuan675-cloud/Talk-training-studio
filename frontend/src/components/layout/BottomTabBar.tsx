import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ClipboardList, Home, MessageSquare, TrendingUp, User } from 'lucide-react'
import { useI18n, type TranslationKey } from '../../i18n'
import './BottomTabBar.css'

interface TabItem {
  to: string
  icon: React.ReactNode
  labelKey: TranslationKey
  elevated?: boolean
  matchPrefix?: string
}

const tabs: TabItem[] = [
  { to: '/', icon: <Home size={20} />, labelKey: 'nav.home' },
  { to: '/chat', icon: <MessageSquare size={20} />, labelKey: 'nav.chat', matchPrefix: '/chat' },
  {
    to: '/scenario-training',
    icon: <ClipboardList size={20} />,
    labelKey: 'nav.scenarioTrainingShort',
    elevated: true,
    matchPrefix: '/scenario-training',
  },
  { to: '/growth', icon: <TrendingUp size={20} />, labelKey: 'nav.growth', matchPrefix: '/growth' },
  { to: '/settings', icon: <User size={20} />, labelKey: 'nav.me', matchPrefix: '/settings' },
]

const BottomTabBar: React.FC = () => {
  const location = useLocation()
  const { t } = useI18n()

  const isActive = (tab: TabItem) => {
    if (tab.to === '/') return location.pathname === '/'
    if (tab.matchPrefix) return location.pathname.startsWith(tab.matchPrefix)
    return false
  }

  return (
    <nav className="bottom-tab-bar">
      {tabs.map((tab) => {
        const active = isActive(tab)
        return (
          <Link
            key={tab.to}
            to={tab.to}
            className={`bottom-tab-item${active ? ' active' : ''}${tab.elevated ? ' elevated' : ''}`}
          >
            {tab.elevated ? (
              <span className="bottom-tab-elevated-icon">{tab.icon}</span>
            ) : (
              <span className="bottom-tab-icon">{tab.icon}</span>
            )}
            <span className="bottom-tab-label">{t(tab.labelKey)}</span>
          </Link>
        )
      })}
    </nav>
  )
}

export default BottomTabBar
