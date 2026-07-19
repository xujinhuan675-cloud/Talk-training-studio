import React, { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { useI18n } from '../../i18n'
import { desktopNavSections, isNavItemActive } from './navigation'
import './NavRail.css'

const STORAGE_KEY = 'talkwise.navrail.collapsed'

const NavRail: React.FC = () => {
  const location = useLocation()
  const { t, tr } = useI18n()
  const { hasAnySystemRole } = useAuthContext()
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(STORAGE_KEY) === 'true'
  })

  const visibleSections = desktopNavSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        if (!item.roles) return true
        return hasAnySystemRole(item.roles)
      }),
    }))
    .filter((section) => section.items.length > 0)

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, String(collapsed))
  }, [collapsed])

  const toggleLabel = collapsed ? tr('展开侧边栏', 'Expand sidebar') : tr('收起侧边栏', 'Collapse sidebar')
  const toggleText = collapsed ? tr('展开', 'Expand') : tr('收起', 'Collapse')
  return (
    <nav className={`navrail${collapsed ? ' navrail--collapsed' : ''}`} aria-label={tr('主导航', 'Primary navigation')}>
      <div className="navrail-content">
        {visibleSections.map((section) => (
          <div className="navrail-section" key={section.id}>
            {!collapsed ? (
              <div className="navrail-section-label">{t(section.labelKey)}</div>
            ) : null}
            <div className="navrail-section-items">
              {section.items.map((item) => {
                const active = isNavItemActive(location.pathname, item)

                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={`navrail-link${active ? ' active' : ''}`}
                    title={t(item.labelKey)}
                    aria-label={t(item.labelKey)}
                    aria-current={active ? 'page' : undefined}
                  >
                    <span className="navrail-link-icon" aria-hidden="true">
                      {item.icon}
                    </span>
                    <span className="navrail-link-label">{t(item.labelKey)}</span>
                  </Link>
                )
              })}
            </div>
          </div>
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
