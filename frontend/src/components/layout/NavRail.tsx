import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuthContext } from '../../contexts/AuthContext'
import { useI18n } from '../../i18n'
import { desktopNavSections, isNavItemActive } from './navigation'
import './NavRail.css'

interface NavRailProps {
  collapsed?: boolean
}

const NavRail: React.FC<NavRailProps> = ({ collapsed = false }) => {
  const location = useLocation()
  const { t, tr } = useI18n()
  const { isAdmin } = useAuthContext()

  const visibleSections = desktopNavSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => !item.requiresAdmin || isAdmin),
    }))
    .filter((section) => section.items.length > 0)

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
    </nav>
  )
}

export default NavRail
