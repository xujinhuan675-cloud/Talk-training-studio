import React from 'react'
import { Loader2, X } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { useI18n } from '../../i18n'
import {
  buildNewApiLoginUrl,
  clearNewApiAutoSignInSuppression,
  NEWAPI_LOGIN_MODE,
  parseNewApiTalkWiseHandoffMessage,
} from '../../services/auth'
import { Button } from '../ui/button'
import '../../pages/LoginPage.css'

interface CredentialLoginPanelProps {
  className?: string
  headingId?: string
  showHeading?: boolean
  returnTo?: string
  onAuthenticated?: () => void
}

// Kept under its existing name while callers move to the control-plane handoff.
export default function CredentialLoginPanel({
  className,
  headingId = 'login-page-title',
  showHeading = true,
  returnTo,
  onAuthenticated,
}: CredentialLoginPanelProps) {
  const { connectNewApiCode } = useAuthContext()
  const { tr } = useI18n()
  const [isRedirecting, setIsRedirecting] = React.useState(false)
  const [isEmbeddedOpen, setIsEmbeddedOpen] = React.useState(NEWAPI_LOGIN_MODE === 'embedded')
  const [isConnecting, setIsConnecting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const iframeRef = React.useRef<HTMLIFrameElement>(null)
  const consumedCodesRef = React.useRef(new Set<string>())
  const loginUrl = React.useMemo(() => buildNewApiLoginUrl(returnTo), [returnTo])

  const completeHandoff = React.useCallback((code: string, redirectUri: string | null) => {
    if (consumedCodesRef.current.has(code)) return
    consumedCodesRef.current.add(code)

    setError(null)
    setIsConnecting(true)
    void connectNewApiCode(code, redirectUri, 'session')
      .then(() => {
        setIsEmbeddedOpen(false)
        onAuthenticated?.()
      })
      .catch((err) => {
        consumedCodesRef.current.delete(code)
        setError(err instanceof Error ? err.message : tr('登录失败', 'Sign-in failed'))
      })
      .finally(() => {
        setIsConnecting(false)
      })
  }, [connectNewApiCode, onAuthenticated, tr])

  const handleHandoffMessage = React.useCallback((event: MessageEvent) => {
    if (iframeRef.current?.contentWindow && event.source !== iframeRef.current.contentWindow) return
    const handoff = parseNewApiTalkWiseHandoffMessage(event)
    if (!handoff) return
    completeHandoff(handoff.code, handoff.redirectUri)
  }, [completeHandoff])

  const handleEmbeddedLoad = React.useCallback(() => {
    try {
      const frameLocation = iframeRef.current?.contentWindow?.location
      if (!frameLocation) return
      if (frameLocation.origin !== window.location.origin || frameLocation.pathname !== '/login') return
      const params = new URLSearchParams(frameLocation.search)
      const code = params.get('talkwise_code') || params.get('code')
      if (!code) return
      completeHandoff(code, `${frameLocation.origin}${frameLocation.pathname}`)
    } catch {
      // Cross-origin frame access is expected while the account form is open.
    }
  }, [completeHandoff])

  React.useEffect(() => {
    if (!isEmbeddedOpen) return
    clearNewApiAutoSignInSuppression()
    window.addEventListener('message', handleHandoffMessage)
    return () => window.removeEventListener('message', handleHandoffMessage)
  }, [handleHandoffMessage, isEmbeddedOpen])

  const handleSignIn = () => {
    clearNewApiAutoSignInSuppression()
    setError(null)
    if (NEWAPI_LOGIN_MODE === 'embedded') {
      setIsEmbeddedOpen(true)
      return
    }
    setIsRedirecting(true)
    window.location.assign(loginUrl)
  }

  const closeEmbeddedLogin = () => {
    if (isConnecting) return
    setIsEmbeddedOpen(false)
  }

  return (
    <section className={`login-panel${className ? ` ${className}` : ''}`}>
      {showHeading ? (
        <div className="login-panel-heading">
          <h1 id={headingId}>{tr('登录', 'Sign in')}</h1>
        </div>
      ) : null}

      {!isEmbeddedOpen ? (
        <Button
          className="login-submit"
          type="button"
          variant="primary"
          disabled={isRedirecting || isConnecting}
          onClick={handleSignIn}
        >
          {isRedirecting ? <Loader2 size={16} aria-hidden="true" /> : null}
          <span>{tr('继续登录', 'Continue to sign in')}</span>
        </Button>
      ) : null}

      {isEmbeddedOpen ? (
        <div className="login-embedded-shell" aria-label={tr('账号登录', 'Account sign-in')}>
          <div className="login-embedded-toolbar">
            <span>{tr('账号登录', 'Account sign-in')}</span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={tr('关闭登录', 'Close sign-in')}
              title={tr('关闭登录', 'Close sign-in')}
              disabled={isConnecting}
              onClick={closeEmbeddedLogin}
            >
              <X size={16} aria-hidden="true" />
            </Button>
          </div>
          <iframe
            ref={iframeRef}
            title={tr('账号登录', 'Account sign-in')}
            src={loginUrl}
            onLoad={handleEmbeddedLoad}
          />
          {isConnecting ? (
            <div className="login-status" role="status" aria-live="polite">
              <Loader2 size={14} aria-hidden="true" />
              <span>{tr('正在连接账号', 'Connecting account')}</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {error ? <div className="login-error" role="alert">{error}</div> : null}
    </section>
  )
}
