import React from 'react'
import { ExternalLink, KeyRound, Loader2, RefreshCw } from 'lucide-react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import {
  buildNewApiLoginUrl,
  canReadSameOriginNewApiStorage,
  NEWAPI_BASE_URL,
  NEWAPI_LOGIN_MODE,
} from '../services/auth'
import { Button } from '../components/ui/button'
import './LoginPage.css'

function redirectTargetFromLocation(state: unknown): string {
  const record = state && typeof state === 'object' ? state as Record<string, unknown> : null
  const from = record?.from
  if (from && typeof from === 'object') {
    const location = from as { pathname?: unknown; search?: unknown }
    const pathname = typeof location.pathname === 'string' ? location.pathname : APP_ROUTES.workbench
    const search = typeof location.search === 'string' ? location.search : ''
    if (pathname !== APP_ROUTES.login) return `${pathname}${search}`
  }
  return APP_ROUTES.workbench
}

const LoginPage: React.FC = () => {
  const { currentUser, connectNewApiToken, connectStoredNewApiSession } = useAuthContext()
  const location = useLocation()
  const { tr } = useI18n()
  const [tokenInput, setTokenInput] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [isConnecting, setIsConnecting] = React.useState(false)
  const [isAutoConnecting, setIsAutoConnecting] = React.useState(false)
  const [autoAttempted, setAutoAttempted] = React.useState(false)
  const [redirectStarted, setRedirectStarted] = React.useState(false)
  const redirectTarget = redirectTargetFromLocation(location.state)
  const loginUrl = React.useMemo(
    () => buildNewApiLoginUrl(typeof window === 'undefined' ? undefined : window.location.href),
    [],
  )
  const canUseEmbeddedSession = canReadSameOriginNewApiStorage()
  const shouldEmbedNewApi = NEWAPI_LOGIN_MODE === 'embedded' && canUseEmbeddedSession

  const tryConnectStoredSession = React.useCallback(async () => {
    setError(null)
    setIsAutoConnecting(true)
    try {
      const nextState = await connectStoredNewApiSession()
      if (!nextState) {
        setAutoAttempted(true)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : tr('登录失败', 'Sign-in failed'))
      setAutoAttempted(true)
    } finally {
      setIsAutoConnecting(false)
    }
  }, [connectStoredNewApiSession, tr])

  React.useEffect(() => {
    if (currentUser || autoAttempted) return
    void tryConnectStoredSession()
  }, [autoAttempted, currentUser, tryConnectStoredSession])

  React.useEffect(() => {
    if (currentUser || redirectStarted || !autoAttempted || NEWAPI_LOGIN_MODE !== 'redirect') return
    setRedirectStarted(true)
    window.location.assign(loginUrl)
  }, [autoAttempted, currentUser, loginUrl, redirectStarted])

  if (currentUser) {
    return <Navigate to={redirectTarget} replace />
  }

  if (redirectStarted) {
    return (
      <main className="login-page" aria-labelledby="login-page-title">
        <section className="login-panel">
          <div className="login-panel-heading">
            <span className="login-panel-kicker">TalkWise</span>
            <h1 id="login-page-title">{tr('正在打开 NewAPI', 'Opening NewAPI')}</h1>
            <p>{tr('请在 NewAPI 完成登录后回到 TalkWise。', 'Complete sign-in in NewAPI, then return to TalkWise.')}</p>
          </div>
          <div className="login-status" role="status" aria-live="polite">
            <Loader2 size={16} aria-hidden="true" />
            <span>{tr('跳转中', 'Redirecting')}</span>
          </div>
        </section>
      </main>
    )
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const token = tokenInput.trim()
    if (!token) {
      setError(tr('请输入 NewAPI token', 'Enter a NewAPI token'))
      return
    }
    setError(null)
    setIsConnecting(true)
    try {
      await connectNewApiToken(token, 'session')
      setTokenInput('')
    } catch (err) {
      setError(err instanceof Error ? err.message : tr('登录失败', 'Sign-in failed'))
    } finally {
      setIsConnecting(false)
    }
  }

  return (
    <main className="login-page" aria-labelledby="login-page-title">
      <section className="login-panel">
        <div className="login-panel-heading">
          <span className="login-panel-kicker">TalkWise</span>
          <h1 id="login-page-title">{tr('登录', 'Sign in')}</h1>
          <p>{tr('使用 NewAPI 账号进入训练工作台。', 'Use your NewAPI account to enter the training workspace.')}</p>
        </div>

        {shouldEmbedNewApi ? (
          <div className="login-embedded-shell">
            <iframe
              title="NewAPI sign-in"
              src={loginUrl}
              onLoad={() => {
                void tryConnectStoredSession()
              }}
            />
            <Button
              className="login-refresh-session"
              type="button"
              variant="secondary"
              disabled={isAutoConnecting}
              onClick={() => {
                void tryConnectStoredSession()
              }}
            >
              {isAutoConnecting ? <Loader2 size={16} aria-hidden="true" /> : <RefreshCw size={16} aria-hidden="true" />}
              <span>{tr('已登录，继续', 'Continue after sign-in')}</span>
            </Button>
          </div>
        ) : (
          <a className="login-newapi-link" href={loginUrl} rel="noreferrer">
            <ExternalLink size={16} aria-hidden="true" />
            <span>{tr('打开 NewAPI 登录页', 'Open NewAPI sign-in')}</span>
          </a>
        )}

        {isAutoConnecting ? (
          <div className="login-status" role="status" aria-live="polite">
            <Loader2 size={14} aria-hidden="true" />
            <span>{tr('正在检查 NewAPI 登录态', 'Checking NewAPI sign-in')}</span>
          </div>
        ) : null}

        <form className="login-token-form" onSubmit={handleSubmit}>
          <label htmlFor="newapi-token-input">NewAPI access token</label>
          <div className="login-token-row">
            <KeyRound size={16} aria-hidden="true" />
            <input
              id="newapi-token-input"
              type="password"
              value={tokenInput}
              autoComplete="off"
              placeholder="Access token"
              onChange={(event) => setTokenInput(event.target.value)}
            />
          </div>
          <Button className="login-submit" type="submit" disabled={isConnecting}>
            {isConnecting ? <Loader2 size={16} aria-hidden="true" /> : <KeyRound size={16} aria-hidden="true" />}
            <span>{isConnecting ? tr('连接中', 'Connecting') : tr('进入 TalkWise', 'Enter TalkWise')}</span>
          </Button>
          {error ? <div className="login-error" role="alert">{error}</div> : null}
        </form>

        <div className="login-meta">
          <span>NewAPI {NEWAPI_LOGIN_MODE}</span>
          <span>{NEWAPI_BASE_URL}</span>
        </div>
      </section>
    </main>
  )
}

export default LoginPage
