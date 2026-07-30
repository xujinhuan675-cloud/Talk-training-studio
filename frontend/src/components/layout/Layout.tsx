import React, { useState, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import TopBar from './TopBar'
import NavRail from './NavRail'
import BottomTabBar from './BottomTabBar'
import CommandPalette from './CommandPalette'
import { useCommandPalette } from '../../hooks/useCommandPalette'
import { useAppContext } from '../../contexts/AppContext'
import { fetchRooms, type ChatRoom } from '../../services/api'
import { getTrainingSessionIdFromLocation } from '../../services/trainingMode'
import './Layout.css'

const NAV_COLLAPSED_STORAGE_KEY = 'talkwise.navrail.collapsed'

const Layout: React.FC = () => {
  const { personaMap } = useAppContext()
  const location = useLocation()
  const [rooms, setRooms] = useState<ChatRoom[]>([])
  const [navCollapsed, setNavCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(NAV_COLLAPSED_STORAGE_KEY) === 'true'
  })

  useEffect(() => {
    fetchRooms()
      .then(setRooms)
      .catch(() => {})
  }, [])

  useEffect(() => {
    window.localStorage.setItem(NAV_COLLAPSED_STORAGE_KEY, String(navCollapsed))
  }, [navCollapsed])

  const palette = useCommandPalette(rooms, personaMap)
  const isTrainingChatRoute = (
    /^\/conversations\/[^/]+/.test(location.pathname)
  ) && Boolean(getTrainingSessionIdFromLocation(location.search, location.state))

  return (
    <div
      className={`app-layout-shell${isTrainingChatRoute ? ' immersive-chat-layout' : ''}`}
      data-shell="platform"
    >
      <TopBar
        navCollapsed={navCollapsed}
        onNavToggle={() => setNavCollapsed((value) => !value)}
        onSearchClick={palette.open}
      />
      <div className="app-body" data-sidebar={navCollapsed ? 'collapsed' : 'expanded'}>
        <NavRail collapsed={navCollapsed} />
        <main className="app-content" id="main-content">
          <Outlet />
        </main>
      </div>
      <BottomTabBar />
      <CommandPalette
        isOpen={palette.isOpen}
        query={palette.query}
        results={palette.results}
        selectedIndex={palette.selectedIndex}
        onClose={palette.close}
        onQueryChange={palette.setQuery}
      />
    </div>
  )
}

export default Layout
