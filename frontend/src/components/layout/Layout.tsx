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

const Layout: React.FC = () => {
  const { personaMap } = useAppContext()
  const location = useLocation()
  const [rooms, setRooms] = useState<ChatRoom[]>([])

  useEffect(() => {
    fetchRooms()
      .then(setRooms)
      .catch(() => {})
  }, [])

  const palette = useCommandPalette(rooms, personaMap)
  const isTrainingChatRoute = /^\/chat\/[^/]+/.test(location.pathname)
    && Boolean(getTrainingSessionIdFromLocation(location.search, location.state))

  return (
    <div className={`app-layout-shell${isTrainingChatRoute ? ' immersive-chat-layout' : ''}`}>
      <TopBar onSearchClick={palette.open} />
      <div className="app-body">
        <NavRail />
        <main className="app-content">
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
