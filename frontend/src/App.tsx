import type { ReactNode } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Layout from './components/layout/Layout'
import HomePage from './pages/HomePage'
import ChatPage from './pages/ChatPage'
import TrainingStudioPage from './pages/TrainingStudioPage'
import ScenarioTrainingPage from './pages/ScenarioTrainingPage'
import ScenarioConfigPage from './pages/ScenarioConfigPage'
import ScenarioLeaderboardPage from './pages/ScenarioLeaderboardPage'
import TrainingHistoryPage from './pages/TrainingHistoryPage'
import TrainingResultPage from './pages/TrainingResultPage'
import BattlePrepPage from './pages/BattlePrepPage'
import DefensePrepPage from './pages/DefensePrepPage'
import GrowthPage from './pages/GrowthPage'
import SettingsPage from './pages/SettingsPage'
import PersonaBuilderPage from './pages/PersonaBuilderPage'
import PersonaEditorPage from './pages/PersonaEditorPage'
import { AppProvider } from './contexts/AppContext'
import { AuthProvider, useAuthContext } from './contexts/AuthContext'
import { I18nProvider } from './i18n'
import { MANAGEMENT_SYSTEM_ROLES, type SystemRole } from './services/auth'

function RequireSystemRole({
  roles,
  children,
}: {
  roles: readonly SystemRole[]
  children: ReactNode
}) {
  const location = useLocation()
  const { canUseMemberWorkspace, hasAnySystemRole } = useAuthContext()

  if (!canUseMemberWorkspace) {
    return <Navigate to="/" replace state={{ from: location }} />
  }

  if (!hasAnySystemRole(roles)) {
    return <Navigate to="/scenario-training" replace state={{ from: location }} />
  }

  return <>{children}</>
}

function managementOnly(element: ReactNode) {
  return <RequireSystemRole roles={MANAGEMENT_SYSTEM_ROLES}>{element}</RequireSystemRole>
}

function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <AppProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<HomePage />} />
              <Route path="training-studio" element={managementOnly(<TrainingStudioPage />)} />
              <Route path="live-coach" element={managementOnly(<TrainingStudioPage initialProfile="live_coach" />)} />
              <Route path="scenario-training" element={<ScenarioTrainingPage />} />
              <Route path="scenario-leaderboard" element={<ScenarioLeaderboardPage />} />
              <Route path="scenario-config" element={managementOnly(<ScenarioConfigPage />)} />
              <Route path="training-history" element={<TrainingHistoryPage />} />
              <Route path="training-result" element={<TrainingResultPage />} />
              <Route path="training-result/:sessionId" element={<TrainingResultPage />} />
              <Route path="training/history" element={<TrainingHistoryPage />} />
              <Route path="training/result" element={<TrainingResultPage />} />
              <Route path="training/result/:sessionId" element={<TrainingResultPage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:roomId" element={<ChatPage />} />
              <Route path="battle-prep" element={managementOnly(<BattlePrepPage />)} />
              <Route path="defense-prep" element={<DefensePrepPage />} />
              <Route path="growth" element={<GrowthPage />} />
              <Route path="settings" element={managementOnly(<SettingsPage />)} />
              <Route path="persona/new" element={managementOnly(<PersonaBuilderPage />)} />
              <Route path="persona/:id/edit" element={managementOnly(<PersonaEditorPage />)} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AppProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

export default App
