import React from 'react'
import { KeyRound, Loader2, RefreshCw } from 'lucide-react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import {
  buildNewApiLoginUrl,
  clearNewApiAutoSignInSuppression,
  isNewApiAutoSignInSuppressed,
  NEWAPI_AUTH_ENABLED,
  NEWAPI_BASE_URL,
  NEWAPI_LOGIN_MODE,
  parseNewApiTalkWiseHandoffMessage,
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
  const { status, currentUser, connectNewApiCode, connectNewApiToken, connectStoredNewApiSession } = useAuthContext()
  const location = useLocation()
  const { tr } = useI18n()
  const [tokenInput, setTokenInput] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [isConnecting, setIsConnecting] = React.useState(false)
  const [isAutoConnecting, setIsAutoConnecting] = React.useState(false)
  const [autoAttempted, setAutoAttempted] = React.useState(false)
  const [redirectStarted, setRedirectStarted] = React.useState(false)
  const [autoSignInSuppressed, setAutoSignInSuppressed] = React.useState(() => isNewApiAutoSignInSuppressed())
  const redirectTarget = redirectTargetFromLocation(location.state)
  const loginUrl = React.useMemo(
    () => buildNewApiLoginUrl(typeof window === 'undefined' ? undefined : window.location.href),
    [],
  )
  const canAutoUseNewApi = NEWAPI_AUTH_ENABLED && !autoSignInSuppressed
  const isRedirectLogin = canAutoUseNewApi && NEWAPI_LOGIN_MODE === 'redirect'
  const shouldUseEmbeddedShell = canAutoUseNewApi && NEWAPI_LOGIN_MODE === 'embedded'
  const shouldShowReconnect = NEWAPI_AUTH_ENABLED && autoSignInSuppressed
  const shouldShowTokenFallback = !NEWAPI_AUTH_ENABLED
  const shouldWaitForAuthSession = canAutoUseNewApi && status === 'loading'

  const allowNewApiSignIn = React.useCallback(() => {
    clearNewApiAutoSignInSuppression()
    setAutoSignInSuppressed(false)
    setAutoAttempted(false)
    setError(null)
  }, [])

  const tryConnectStoredSession = React.useCallback(async () => {
    if (isNewApiAutoSignInSuppressed()) {
      setAutoSignInSuppressed(true)
      setAutoAttempted(true)
      return
    }
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
    if (currentUser || autoSignInSuppressed || autoAttempted || shouldWaitForAuthSession) return
    void tryConnectStoredSession()
  }, [autoAttempted, autoSignInSuppressed, currentUser, shouldWaitForAuthSession, tryConnectStoredSession])

  const handleNewApiHandoffMessage = React.useCallback(
    (event: MessageEvent) => {
      if (isNewApiAutoSignInSuppressed()) {
        setAutoSignInSuppressed(true)
        return
      }
      const handoff = parseNewApiTalkWiseHandoffMessage(event)
      if (!handoff || currentUser) return

      setError(null)
      setIsAutoConnecting(true)
      void connectNewApiCode(handoff.code, handoff.redirectUri, 'session')
        .catch((err) => {
          setError(err instanceof Error ? err.message : tr('Sign-in failed', 'Sign-in failed'))
          setAutoAttempted(true)
        })
        .finally(() => {
          setIsAutoConnecting(false)
        })
    },
    [connectNewApiCode, currentUser, tr],
  )

  React.useEffect(() => {
    if (!shouldUseEmbeddedShell) return undefined
    window.addEventListener('message', handleNewApiHandoffMessage)
    return () => {
      window.removeEventListener('message', handleNewApiHandoffMessage)
    }
  }, [handleNewApiHandoffMessage, shouldUseEmbeddedShell])

  React.useEffect(() => {
    if (
      currentUser ||
      redirectStarted ||
      !autoAttempted ||
      !isRedirectLogin ||
      error ||
      isAutoConnecting ||
      shouldWaitForAuthSession
    ) {
      return
    }
    setRedirectStarted(true)
    window.location.assign(loginUrl)
  }, [
    autoAttempted,
    currentUser,
    error,
    isAutoConnecting,
    isRedirectLogin,
    loginUrl,
    redirectStarted,
    shouldWaitForAuthSession,
  ])

  const retryRedirect = React.useCallback(() => {
    clearNewApiAutoSignInSuppression()
    setAutoSignInSuppressed(false)
    setError(null)
    setAutoAttempted(true)
    setRedirectStarted(true)
    window.location.assign(loginUrl)
  }, [loginUrl])

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

  if (currentUser) {
    return <Navigate to={redirectTarget} replace />
  }

  if (shouldUseEmbeddedShell) {
    return (
      <main className="login-page login-page--embedded" aria-labelledby="login-page-title">
        <section className="login-panel login-panel--embedded">
          <h1 id="login-page-title" className="sr-only">Sign in</h1>
          <div className="login-newapi-shell">
            <iframe
              title="NewAPI sign-in"
              src={loginUrl}
              onLoad={() => {
                void tryConnectStoredSession()
              }}
            />
          </div>
          {isAutoConnecting ? (
            <div className="login-status" role="status" aria-live="polite">
              <Loader2 size={14} aria-hidden="true" />
              <span>{tr('Checking NewAPI sign-in', 'Checking NewAPI sign-in')}</span>
            </div>
          ) : null}
          {error ? <div className="login-error" role="alert">{error}</div> : null}
        </section>
      </main>
    )
  }

  if (isRedirectLogin || redirectStarted) {
    return (
      <main className="login-page" aria-labelledby="login-page-title">
        <section className="login-panel">
          <div className="login-panel-heading">
            <span className="login-panel-kicker">TalkWise</span>
            <h1 id="login-page-title">{tr('正在打开 NewAPI', 'Opening NewAPI')}</h1>
            <p>{tr('请在 NewAPI 完成登录后回到 TalkWise。', 'Complete sign-in in NewAPI, then return to TalkWise.')}</p>
          </div>
          {error ? (
            <>
              <div className="login-error" role="alert">{error}</div>
              <Button className="login-refresh-session" type="button" variant="secondary" onClick={retryRedirect}>
                <RefreshCw size={16} aria-hidden="true" />
                <span>{tr('重试 NewAPI 登录', 'Retry NewAPI sign-in')}</span>
              </Button>
            </>
          ) : (
            <div className="login-status" role="status" aria-live="polite">
              <Loader2 size={16} aria-hidden="true" />
              <span>
                {shouldWaitForAuthSession || isAutoConnecting
                  ? tr('正在检查 NewAPI 登录状态', 'Checking NewAPI sign-in')
                  : tr('跳转中', 'Redirecting')}
              </span>
            </div>
          )}
        </section>
      </main>
    )
  }

  return (
    <main className="login-page" aria-labelledby="login-page-title">
      <section className="login-panel">
        <div className="login-panel-heading">
          <span className="login-panel-kicker">TalkWise</span>
          <h1 id="login-page-title">{tr('登录', 'Sign in')}</h1>
          <p>{tr('使用 NewAPI 账号进入训练工作台。', 'Use your NewAPI account to enter the training workspace.')}</p>
        </div>

        {shouldShowReconnect ? (
          <Button className="login-submit" type="button" variant="secondary" onClick={allowNewApiSignIn}>
            <RefreshCw size={16} aria-hidden="true" />
            <span>{tr('继续 NewAPI 登录', 'Continue NewAPI sign-in')}</span>
          </Button>
        ) : null}

        {isAutoConnecting ? (
          <div className="login-status" role="status" aria-live="polite">
            <Loader2 size={14} aria-hidden="true" />
            <span>{tr('正在检查 NewAPI 登录态', 'Checking NewAPI sign-in')}</span>
          </div>
        ) : null}

        {shouldShowTokenFallback ? (
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
        ) : null}

        {!NEWAPI_AUTH_ENABLED ? (
          <div className="login-meta">
            <span>NewAPI {NEWAPI_LOGIN_MODE}</span>
            <span>{NEWAPI_BASE_URL}</span>
          </div>
        ) : null}
      </section>
    </main>
  )
}

export default LoginPage
