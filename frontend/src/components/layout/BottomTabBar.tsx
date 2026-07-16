import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ClipboardList, History, Home, SlidersHorizontal, TrendingUp } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { useI18n, type TranslationKey } from '../../i18n'
import { MANAGEMENT_SYSTEM_ROLES, type SystemRole } from '../../services/auth'
import './BottomTabBar.css'

interface TabItem {
  to: string
  icon: React.ReactNode
  labelKey: TranslationKey
  elevated?: boolean
  matchPrefix?: string
  roles?: readonly SystemRole[]
}

const tabs: TabItem[] = [
  { to: '/', icon: <Home size={20} />, labelKey: 'nav.home' },
  {
    to: '/scenario-training',
    icon: <ClipboardList size={20} />,
    labelKey: 'nav.scenarioTrainingShort',
    elevated: true,
    matchPrefix: '/scenario-training',
  },
  { to: '/training-history', icon: <History size={20} />, labelKey: 'nav.trainingHistory', matchPrefix: '/training-history' },
  { to: '/growth', icon: <TrendingUp size={20} />, labelKey: 'nav.growth', matchPrefix: '/growth' },
  {
    to: '/scenario-config',
    icon: <SlidersHorizontal size={20} />,
    labelKey: 'nav.scenarioConfig',
    matchPrefix: '/scenario-config',
    roles: MANAGEMENT_SYSTEM_ROLES,
  },
]

const BottomTabBar: React.FC = () => {
  const location = useLocation()
  const { t } = useI18n()
  const { hasAnySystemRole } = useAuthContext()

  const visibleTabs = tabs.filter((tab) => {
    if (!tab.roles) return true
    return hasAnySystemRole(tab.roles)
  })

  const isActive = (tab: TabItem) => {
    if (tab.to === '/') return location.pathname === '/'
    if (tab.matchPrefix) return location.pathname.startsWith(tab.matchPrefix)
    return false
  }

  return (
    <nav className="bottom-tab-bar">
      {visibleTabs.map((tab) => {
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
