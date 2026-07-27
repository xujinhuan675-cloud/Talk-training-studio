import React from 'react'
import { Eye, EyeOff, Loader2, Lock, Mail } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { useI18n } from '../../i18n'
import {
  clearNewApiAutoSignInSuppression,
  isNewApiAutoSignInSuppressed,
  NEWAPI_AUTH_ENABLED,
  NEWAPI_BASE_URL,
} from '../../services/auth'
import { Button } from '../ui/button'
import '../../pages/LoginPage.css'

interface CredentialLoginPanelProps {
  className?: string
  headingId?: string
  showHeading?: boolean
  autoCheckStoredSession?: boolean
  onAuthenticated?: () => void
}

function newApiUrl(pathname: string): string {
  try {
    return new URL(pathname, `${NEWAPI_BASE_URL.replace(/\/+$/, '')}/`).toString()
  } catch {
    return NEWAPI_BASE_URL
  }
}

export default function CredentialLoginPanel({
  className,
  headingId = 'login-page-title',
  showHeading = true,
  autoCheckStoredSession = true,
  onAuthenticated,
}: CredentialLoginPanelProps) {
  const { status, currentUser, connectNewApiCredentials, connectStoredNewApiSession } = useAuthContext()
  const { tr } = useI18n()
  const [usernameInput, setUsernameInput] = React.useState('')
  const [passwordInput, setPasswordInput] = React.useState('')
  const [isPasswordVisible, setIsPasswordVisible] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [isConnecting, setIsConnecting] = React.useState(false)
  const [isAutoConnecting, setIsAutoConnecting] = React.useState(false)
  const [autoAttempted, setAutoAttempted] = React.useState(false)
  const [autoSignInSuppressed, setAutoSignInSuppressed] = React.useState(() => isNewApiAutoSignInSuppressed())
  const registerUrl = React.useMemo(() => newApiUrl('/register'), [])
  const forgotPasswordUrl = React.useMemo(() => newApiUrl('/login'), [])
  const shouldWaitForAuthSession = NEWAPI_AUTH_ENABLED && status === 'loading'
  const isSubmitting = isConnecting || isAutoConnecting

  const tryConnectStoredSession = React.useCallback(async () => {
    if (!autoCheckStoredSession) return
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
  }, [autoCheckStoredSession, connectStoredNewApiSession, tr])

  React.useEffect(() => {
    if (currentUser) {
      onAuthenticated?.()
      return
    }
    if (!autoCheckStoredSession || autoSignInSuppressed || autoAttempted || shouldWaitForAuthSession) return
    void tryConnectStoredSession()
  }, [
    autoAttempted,
    autoCheckStoredSession,
    autoSignInSuppressed,
    currentUser,
    onAuthenticated,
    shouldWaitForAuthSession,
    tryConnectStoredSession,
  ])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const username = usernameInput.trim()
    if (!username || !passwordInput) {
      setError(tr('请输入用户名或邮箱和密码', 'Enter your username or email and password'))
      return
    }

    setError(null)
    setIsConnecting(true)
    clearNewApiAutoSignInSuppression()
    setAutoSignInSuppressed(false)
    try {
      await connectNewApiCredentials(username, passwordInput, 'session')
      setPasswordInput('')
      onAuthenticated?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : tr('登录失败', 'Sign-in failed'))
    } finally {
      setIsConnecting(false)
    }
  }

  return (
    <section className={`login-panel${className ? ` ${className}` : ''}`}>
      {showHeading ? (
        <div className="login-panel-heading">
          <h1 id={headingId}>{tr('登录', 'Sign in')}</h1>
        </div>
      ) : null}

      <form className="login-credential-form" onSubmit={handleSubmit}>
        <div className="login-field">
          <label className="login-field-label" htmlFor="newapi-username-input">
            {tr('用户名或邮箱', 'Username or email')}
          </label>
          <div className="login-field-control">
            <Mail className="login-field-icon" size={18} aria-hidden="true" />
            <input
              id="newapi-username-input"
              type="text"
              value={usernameInput}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              disabled={isSubmitting}
              onChange={(event) => setUsernameInput(event.target.value)}
            />
          </div>
        </div>

        <div className="login-field">
          <label className="login-field-label" htmlFor="newapi-password-input">
            {tr('密码', 'Password')}
          </label>
          <div className="login-field-control">
            <Lock className="login-field-icon" size={18} aria-hidden="true" />
            <input
              id="newapi-password-input"
              type={isPasswordVisible ? 'text' : 'password'}
              value={passwordInput}
              autoComplete="current-password"
              disabled={isSubmitting}
              onChange={(event) => setPasswordInput(event.target.value)}
            />
            <button
              className="login-password-toggle"
              type="button"
              aria-label={isPasswordVisible ? tr('隐藏密码', 'Hide password') : tr('显示密码', 'Show password')}
              disabled={isSubmitting}
              onClick={() => setIsPasswordVisible((visible) => !visible)}
            >
              {isPasswordVisible ? (
                <EyeOff size={18} aria-hidden="true" />
              ) : (
                <Eye size={18} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        <Button className="login-submit" type="submit" variant="primary" disabled={isSubmitting}>
          {isConnecting ? <Loader2 size={16} aria-hidden="true" /> : null}
          <span>{tr('继续', 'Continue')}</span>
        </Button>
      </form>

      <a className="login-forgot-link" href={forgotPasswordUrl} target="_blank" rel="noreferrer">
        {tr('忘记密码?', 'Forgot password?')}
      </a>

      <div className="login-register">
        <span>{tr('没有账户?', 'No account?')}</span>
        <a href={registerUrl} target="_blank" rel="noreferrer">
          {tr('注册', 'Register')}
        </a>
      </div>

      {isAutoConnecting ? (
        <div className="login-status" role="status" aria-live="polite">
          <Loader2 size={14} aria-hidden="true" />
          <span>{tr('正在检查登录状态', 'Checking sign-in')}</span>
        </div>
      ) : null}

      {error ? <div className="login-error" role="alert">{error}</div> : null}
    </section>
  )
}
