import { Suspense, lazy, useEffect, type ReactNode } from 'react'
import { Routes, Route, Navigate, Outlet, useLocation, useParams } from 'react-router-dom'
import AuthPromptDialog from './components/auth/AuthPromptDialog'
import Layout from './components/layout/Layout'
import { AppProvider } from './contexts/AppContext'
import { AuthProvider, useAuthContext } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { I18nProvider, useI18n } from './i18n'
import { APP_ROUTES } from './appRoutes'
import {
  createRedirectTarget,
  resolveConversationRoomRedirectTarget,
  resolvePersonaEditRedirectTarget,
  resolveTrainingResultSessionRedirectTarget,
} from './routeRedirects'
import { getDocumentTitle } from './routeTitles'

const HomePage = lazy(() => import('./pages/HomePage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const PublicLandingPage = lazy(() => import('./pages/PublicLandingPage'))
const ChatPage = lazy(() => import('./pages/ChatPage'))
const TrainingStudioPage = lazy(() => import('./pages/TrainingStudioPage'))
const ScenarioTrainingPage = lazy(() => import('./pages/ScenarioTrainingPage'))
const ScenarioConfigPage = lazy(() => import('./pages/ScenarioConfigPage'))
const ScenarioLeaderboardPage = lazy(() => import('./pages/ScenarioLeaderboardPage'))
const TrainingHistoryPage = lazy(() => import('./pages/TrainingHistoryPage'))
const TrainingResultPage = lazy(() => import('./pages/TrainingResultPage'))
const BattlePrepPage = lazy(() => import('./pages/BattlePrepPage'))
const DefensePrepPage = lazy(() => import('./pages/DefensePrepPage'))
const GrowthPage = lazy(() => import('./pages/GrowthPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const PersonaBuilderPage = lazy(() => import('./pages/PersonaBuilderPage'))
const PersonaEditorPage = lazy(() => import('./pages/PersonaEditorPage'))

function RouteLoadingFallback() {
  const { t } = useI18n()
  return (
    <div className="app-route-loading" role="status" aria-live="polite">
      {t('common.loading')}
    </div>
  )
}

function DocumentTitleSync() {
  const location = useLocation()
  const { t } = useI18n()

  useEffect(() => {
    document.title = getDocumentTitle(location.pathname, location.search, t)
  }, [location.pathname, location.search, t])

  return null
}

function PublicLandingRoute() {
  const { currentUser, isLoading } = useAuthContext()

  if (isLoading) return <RouteLoadingFallback />
  if (currentUser) return <Navigate to={APP_ROUTES.workbench} replace />
  return <PublicLandingPage />
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const location = useLocation()
  const { currentUser, isAdmin } = useAuthContext()

  if (currentUser && !isAdmin) {
    return <Navigate to={APP_ROUTES.practiceScenarios} replace state={{ from: location }} />
  }

  return <>{children}</>
}

function managementOnly(element: ReactNode) {
  return <RequireAdmin>{element}</RequireAdmin>
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
      <ThemeProvider>
        <AuthProvider>
          <DocumentTitleSync />
          <AuthPromptDialog />
          <Suspense fallback={<RouteLoadingFallback />}>
            <Routes>
              <Route path="login" element={<LoginPage />} />
              <Route index element={<PublicLandingRoute />} />
              <Route element={<AppProvider><Layout /></AppProvider>}>
                <Route path="workspace" element={<HomePage />} />
                <Route path="practice" element={<Outlet />}>
                  <Route index element={<RedirectTo to={APP_ROUTES.practiceScenarios} />} />
                  <Route path="scenarios" element={<ScenarioTrainingPage />} />
                  <Route path="custom" element={managementOnly(<TrainingStudioPage />)} />
                  <Route path="live-coach" element={managementOnly(<TrainingStudioPage initialProfile="live_coach" />)} />
                  <Route path="defense-prep" element={<DefensePrepPage />} />
                  <Route path="battle-prep" element={<BattlePrepPage />} />
                </Route>
                <Route path="chat/:roomId" element={<ConversationRoomRedirect />} />
                <Route path="conversations" element={<ChatPage />} />
                <Route path="conversations/:roomId" element={<ChatPage />} />
                <Route path="review" element={<Outlet />}>
                  <Route index element={<RedirectTo to={APP_ROUTES.reviewSessions} />} />
                  <Route path="sessions" element={<TrainingHistoryPage />} />
                  <Route path="sessions/:sessionId" element={<TrainingResultPage />} />
                </Route>
                <Route path="review/session/:sessionId" element={<TrainingResultSessionRedirect />} />
                <Route path="growth" element={<GrowthPage />} />
                <Route path="growth/leaderboard" element={<ScenarioLeaderboardPage />} />
                <Route path="config" element={<SettingsPage />} />
                <Route path="config/scenarios" element={managementOnly(<ScenarioConfigPage />)} />
                <Route path="config/personas/new" element={<PersonaBuilderPage />} />
                <Route path="config/personas/:id/edit" element={<PersonaEditorPage />} />
                <Route path="config/persona/:id/edit" element={<PersonaEditRedirect />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </AuthProvider>
      </ThemeProvider>
    </I18nProvider>
  )
}

export default App
