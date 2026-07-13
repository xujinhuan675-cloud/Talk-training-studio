import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Dumbbell, Home, MessageSquare, TrendingUp, User } from 'lucide-react'
import './BottomTabBar.css'

interface TabItem {
  to: string
  icon: React.ReactNode
  label: string
  elevated?: boolean
  matchPrefix?: string
}

const tabs: TabItem[] = [
  { to: '/', icon: <Home size={20} />, label: 'Home' },
  { to: '/chat', icon: <MessageSquare size={20} />, label: 'Chat', matchPrefix: '/chat' },
  {
    to: '/training-studio',
    icon: <Dumbbell size={20} />,
    label: 'Train',
    elevated: true,
    matchPrefix: '/training-studio',
  },
  { to: '/growth', icon: <TrendingUp size={20} />, label: 'Growth', matchPrefix: '/growth' },
  { to: '/settings', icon: <User size={20} />, label: 'Me', matchPrefix: '/settings' },
]

const BottomTabBar: React.FC = () => {
  const location = useLocation()

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
            <span className="bottom-tab-label">{tab.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}

export default BottomTabBar
