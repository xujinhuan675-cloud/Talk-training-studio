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
  return <Navigate to={`${to}${location.search}`} replace state={location.state} />
}

function LegacyConversationRedirect() {
  const { roomId } = useParams()
  const location = useLocation()
  const target = roomId ? APP_ROUTES.conversation(roomId) : APP_ROUTES.conversations
  return <Navigate to={`${target}${location.search}`} replace state={location.state} />
}

function LegacyTrainingResultRedirect() {
  const { sessionId } = useParams()
  const location = useLocation()
  const target = sessionId ? APP_ROUTES.reviewSession(sessionId) : APP_ROUTES.reviewSessions
  return <Navigate to={`${target}${location.search}`} replace state={location.state} />
}

function LegacyPersonaEditRedirect() {
  const { id } = useParams()
  const location = useLocation()
  const target = id ? APP_ROUTES.configPersonaEdit(id) : APP_ROUTES.config
  return <Navigate to={`${target}${location.search}`} replace state={location.state} />
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
              <Route path="scenario-training" element={<RedirectTo to={APP_ROUTES.practiceScenarios} />} />
              <Route path="training-studio" element={<RedirectTo to={APP_ROUTES.practiceCustom} />} />
              <Route path="live-coach" element={<RedirectTo to={APP_ROUTES.practiceLiveCoach} />} />
              <Route path="battle-prep" element={<RedirectTo to={APP_ROUTES.practiceBattle} />} />
              <Route path="defense-prep" element={<RedirectTo to={APP_ROUTES.practiceDefense} />} />
              <Route path="chat" element={<LegacyConversationRedirect />} />
              <Route path="chat/:roomId" element={<LegacyConversationRedirect />} />
              <Route path="training-history" element={<RedirectTo to={APP_ROUTES.reviewSessions} />} />
              <Route path="training-result" element={<LegacyTrainingResultRedirect />} />
              <Route path="training-result/:sessionId" element={<LegacyTrainingResultRedirect />} />
              <Route path="training/history" element={<RedirectTo to={APP_ROUTES.reviewSessions} />} />
              <Route path="training/result" element={<LegacyTrainingResultRedirect />} />
              <Route path="training/result/:sessionId" element={<LegacyTrainingResultRedirect />} />
              <Route path="scenario-leaderboard" element={<RedirectTo to={APP_ROUTES.growthLeaderboard} />} />
              <Route path="scenario-config" element={<RedirectTo to={APP_ROUTES.configScenarios} />} />
              <Route path="settings" element={<RedirectTo to={APP_ROUTES.config} />} />
              <Route path="persona/new" element={<RedirectTo to={APP_ROUTES.configPersonaNew} />} />
              <Route path="persona/:id/edit" element={<LegacyPersonaEditRedirect />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AppProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

export default App
