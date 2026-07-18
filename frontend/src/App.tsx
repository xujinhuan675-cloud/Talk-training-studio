import type { ReactNode } from 'react'
import { Routes, Route, Navigate, Outlet, useLocation, useParams } from 'react-router-dom'
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
import { APP_ROUTES } from './appRoutes'
import {
  createRedirectTarget,
  resolveConversationRoomRedirectTarget,
  resolvePersonaEditRedirectTarget,
  resolveTrainingResultSessionRedirectTarget,
} from './routeRedirects'

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
    return <Navigate to={APP_ROUTES.practiceScenarios} replace state={{ from: location }} />
  }

  return <>{children}</>
}

function managementOnly(element: ReactNode) {
  return <RequireSystemRole roles={MANAGEMENT_SYSTEM_ROLES}>{element}</RequireSystemRole>
}

function RedirectTo({ to }: { to: string }) {
  const location = useLocation()
  const redirectTarget = createRedirectTarget(to, location)
  return <Navigate to={redirectTarget.to} replace state={redirectTarget.state} />
}

function ConversationRoomRedirect() {
  const location = useLocation()
  const { roomId } = useParams<{ roomId: string }>()
  const redirectTarget = createRedirectTarget(resolveConversationRoomRedirectTarget(roomId), location)
  return <Navigate to={redirectTarget.to} replace state={redirectTarget.state} />
}

function TrainingResultSessionRedirect() {
  const location = useLocation()
  const { sessionId } = useParams<{ sessionId: string }>()
  const redirectTarget = createRedirectTarget(resolveTrainingResultSessionRedirectTarget(sessionId), location)
  return <Navigate to={redirectTarget.to} replace state={redirectTarget.state} />
}

function PersonaEditRedirect() {
  const location = useLocation()
  const { id } = useParams<{ id: string }>()
  const redirectTarget = createRedirectTarget(resolvePersonaEditRedirectTarget(id), location)
  return <Navigate to={redirectTarget.to} replace state={redirectTarget.state} />
}

function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <AppProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<HomePage />} />
              <Route path="practice" element={<Outlet />}>
                <Route index element={<RedirectTo to={APP_ROUTES.practiceScenarios} />} />
                <Route path="scenarios" element={<ScenarioTrainingPage />} />
                <Route path="custom" element={managementOnly(<TrainingStudioPage />)} />
                <Route path="live-coach" element={managementOnly(<TrainingStudioPage initialProfile="live_coach" />)} />
                <Route path="defense-prep" element={<DefensePrepPage />} />
                <Route path="battle-prep" element={managementOnly(<BattlePrepPage />)} />
              </Route>
              <Route path="conversations" element={<ChatPage />} />
              <Route path="conversations/:roomId" element={<ChatPage />} />
              <Route path="review" element={<Outlet />}>
                <Route index element={<RedirectTo to={APP_ROUTES.reviewSessions} />} />
                <Route path="sessions" element={<TrainingHistoryPage />} />
                <Route path="sessions/:sessionId" element={<TrainingResultPage />} />
              </Route>
              <Route path="growth" element={<GrowthPage />} />
              <Route path="growth/leaderboard" element={<ScenarioLeaderboardPage />} />
              <Route path="config" element={managementOnly(<SettingsPage />)} />
              <Route path="config/scenarios" element={managementOnly(<ScenarioConfigPage />)} />
              <Route path="config/personas/new" element={managementOnly(<PersonaBuilderPage />)} />
              <Route path="config/personas/:id/edit" element={managementOnly(<PersonaEditorPage />)} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AppProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

export default App
