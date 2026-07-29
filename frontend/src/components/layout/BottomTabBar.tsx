import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useI18n } from '../../i18n'
import { isNavItemActive, mobileNavItems } from './navigation'
import './BottomTabBar.css'

const BottomTabBar: React.FC = () => {
  const location = useLocation()
  const { t } = useI18n()

  return (
    <nav className="bottom-tab-bar">
      {mobileNavItems.map((tab) => {
        const active = isNavItemActive(location.pathname, tab)
        return (
          <Link
            key={tab.to}
            to={tab.to}
            className={`bottom-tab-item${active ? ' active' : ''}${tab.elevated ? ' elevated' : ''}`}
          >
            <span className="bottom-tab-icon">{tab.icon}</span>
            <span className="bottom-tab-label">{t(tab.labelKey)}</span>
          </Link>
        )
      })}
    </nav>
  )
}

export default BottomTabBar
