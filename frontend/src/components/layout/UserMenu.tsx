import React from 'react'
import { Check, ChevronDown, ExternalLink, KeyRound, Loader2, LogOut, UserRound } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import {
  buildNewApiLoginUrl,
  getUserDisplayRoleName,
  NEWAPI_API_KEYS_URL,
  NEWAPI_AUTH_ENABLED,
  NEWAPI_CONSOLE_URL,
  NEWAPI_USAGE_URL,
} from '../../services/auth'
import { useI18n } from '../../i18n'
import { Button } from '../ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import './UserMenu.css'

function formatAccountMetric(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-'
  return new Intl.NumberFormat(undefined, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function productNeutralLabel(value: string | null | undefined, fallback: string): string {
  const label = value?.trim()
  if (!label) return fallback
  return /new\s*api/i.test(label) ? fallback : label
}

const UserMenu: React.FC = () => {
  const { currentUser, users, connectNewApiToken, requestSignIn, switchUser, signOut } = useAuthContext()
  const { tr } = useI18n()
  const [tokenInput, setTokenInput] = React.useState('')
  const [connectError, setConnectError] = React.useState<string | null>(null)
  const [isConnecting, setIsConnecting] = React.useState(false)

  const userName = currentUser?.name ?? tr('未登录', 'Signed out')
  const roleName = currentUser ? getUserDisplayRoleName(currentUser) : tr('选择一个模拟用户', 'Choose a mock user')
  const avatarInitial = currentUser?.avatarInitial ?? '?'
  const teamName = currentUser?.teamName ?? tr('未分配团队', 'No team')
  const quotaRemaining = formatAccountMetric(currentUser?.quotaRemaining)
  const quotaUsed = formatAccountMetric(currentUser?.quotaUsed)
  const requestCount = formatAccountMetric(currentUser?.requestCount)
  const planLabel = productNeutralLabel(
    currentUser?.subscriptionPlan || currentUser?.subscriptionStatus,
    tr('默认', 'Default'),
  )
  const currentUserValue = currentUser?.authProvider === 'mock' ? currentUser.id : ''
  const isNewApiUser = currentUser?.authProvider === 'newapi'
  const newApiLoginUrl = React.useMemo(() => buildNewApiLoginUrl(), [])
  const showManualNewApiConnect = !NEWAPI_AUTH_ENABLED

  const handleNewApiSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const token = tokenInput.trim()
    if (!token) {
      setConnectError(tr('请输入访问令牌', 'Enter an access token'))
      return
    }
    setConnectError(null)
    setIsConnecting(true)
    try {
      await connectNewApiToken(token, 'session')
      setTokenInput('')
    } catch (error) {
      const message = error instanceof Error ? error.message : tr('连接失败', 'Connection failed')
      setConnectError(message)
    } finally {
      setIsConnecting(false)
    }
  }

  if (!currentUser) {
    return (
      <Button
        className="user-menu-trigger user-menu-login"
        variant="secondary"
        size="sm"
        type="button"
        aria-label={tr('登录', 'Sign in')}
        title={tr('登录', 'Sign in')}
        onClick={requestSignIn}
      >
        <UserRound size={15} aria-hidden="true" />
        <span>{tr('登录', 'Sign in')}</span>
      </Button>
    )
  }

  return (
    <DropdownMenu>
      <Button
        asChild
        className="user-menu-trigger"
        variant="secondary"
        size="sm"
      >
        <DropdownMenuTrigger
          aria-label={tr('用户菜单', 'User menu')}
          title={currentUser ? `${userName} · ${roleName}` : tr('用户菜单', 'User menu')}
        >
          <span className="user-menu-avatar" aria-hidden="true">
            {avatarInitial}
          </span>
          <span className="user-menu-summary">
            <span className="user-menu-name">{userName}</span>
            <span className="user-menu-role">{roleName}</span>
          </span>
          <ChevronDown className="user-menu-chevron" size={15} aria-hidden="true" />
        </DropdownMenuTrigger>
      </Button>

      <DropdownMenuContent className="user-menu-popover" align="end">
        <div className="user-menu-profile-card">
          <span className="user-menu-profile-avatar" aria-hidden="true">
            {avatarInitial}
          </span>
          <span className="user-menu-profile-copy">
            <span className="user-menu-profile-name">{userName}</span>
            <span className="user-menu-profile-meta">{teamName}</span>
          </span>
        </div>

        <div className="user-menu-account-grid" aria-label={tr('账号概览', 'Account overview')}>
          <span>
            <em>{tr('余额', 'Balance')}</em>
            <strong>{quotaRemaining}</strong>
          </span>
          <span>
            <em>{tr('已用', 'Used')}</em>
            <strong>{quotaUsed}</strong>
          </span>
          <span>
            <em>{tr('请求', 'Requests')}</em>
            <strong>{requestCount}</strong>
          </span>
        </div>

        <div className="user-menu-plan-row">
          <span>{tr('计划', 'Plan')}</span>
          <strong>{planLabel}</strong>
        </div>

        <DropdownMenuSeparator className="user-menu-divider" />

        {!NEWAPI_AUTH_ENABLED ? (
          <>
            <DropdownMenuLabel className="user-menu-heading">{tr('模拟用户', 'Mock users')}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              className="user-menu-options"
              value={currentUserValue}
              aria-label={tr('模拟用户', 'Mock users')}
            >
              {users.map((user) => {
                const selected = currentUser?.authProvider === 'mock' && currentUser.id === user.id
                return (
                  <DropdownMenuRadioItem
                    key={user.id}
                    value={user.id}
                    className={`user-menu-option${selected ? ' selected' : ''}`}
                    onSelect={() => {
                      switchUser(user.id)
                    }}
                  >
                    <span className="user-menu-option-avatar" aria-hidden="true">
                      {user.avatarInitial}
                    </span>
                    <span className="user-menu-option-copy">
                      <span className="user-menu-option-name">{user.name}</span>
                      <span className="user-menu-option-role">{getUserDisplayRoleName(user)}</span>
                    </span>
                    {selected ? <Check size={15} aria-hidden="true" /> : null}
                  </DropdownMenuRadioItem>
                )
              })}
            </DropdownMenuRadioGroup>

            <DropdownMenuSeparator className="user-menu-divider" />
          </>
        ) : null}

        <form
          className="user-menu-newapi"
          onSubmit={handleNewApiSubmit}
          onKeyDown={(event) => {
            event.stopPropagation()
          }}
        >
          <div className="user-menu-newapi-header">
            <span className="user-menu-newapi-title">
              <KeyRound size={14} aria-hidden="true" />
              <span>{tr('账号', 'Account')}</span>
            </span>
            {showManualNewApiConnect ? (
              <a
                className="user-menu-newapi-link"
                href={newApiLoginUrl}
                target="_blank"
                rel="noreferrer"
                aria-label={tr('打开账号控制台', 'Open account console')}
                title={newApiLoginUrl}
              >
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            ) : null}
          </div>

          <div className="user-menu-newapi-links">
            <a href={NEWAPI_CONSOLE_URL} target="_blank" rel="noreferrer">
              <ExternalLink size={13} aria-hidden="true" />
              <span>{tr('控制台', 'Console')}</span>
            </a>
            <a href={NEWAPI_API_KEYS_URL} target="_blank" rel="noreferrer">
              <KeyRound size={13} aria-hidden="true" />
              <span>API Keys</span>
            </a>
            <a href={NEWAPI_USAGE_URL} target="_blank" rel="noreferrer">
              <ExternalLink size={13} aria-hidden="true" />
              <span>{tr('用量', 'Usage')}</span>
            </a>
          </div>

          {isNewApiUser ? (
            <div className="user-menu-newapi-current">
              <span className="user-menu-newapi-dot" aria-hidden="true" />
              <span>{currentUser?.username}</span>
            </div>
          ) : null}

          {showManualNewApiConnect ? (
            <>
              <input
                className="user-menu-newapi-input"
                type="password"
                value={tokenInput}
                autoComplete="off"
                placeholder={tr('访问令牌', 'Access token')}
                aria-label={tr('访问令牌', 'Access token')}
                onChange={(event) => {
                  setTokenInput(event.target.value)
                }}
              />
              <Button
                className="user-menu-newapi-submit"
                type="submit"
                variant="secondary"
                size="sm"
                disabled={isConnecting}
              >
                {isConnecting ? <Loader2 size={14} aria-hidden="true" /> : <KeyRound size={14} aria-hidden="true" />}
                <span>{isConnecting ? tr('连接中', 'Connecting') : tr('连接', 'Connect')}</span>
              </Button>
            </>
          ) : null}
          {showManualNewApiConnect && connectError ? (
            <div className="user-menu-newapi-error" role="alert">
              {connectError}
            </div>
          ) : null}
        </form>

        <DropdownMenuSeparator className="user-menu-divider" />

        <DropdownMenuItem
          className="user-menu-action"
          onSelect={() => {
            signOut()
          }}
        >
          <LogOut size={15} aria-hidden="true" />
          <span>{tr('退出登录', 'Sign out')}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default UserMenu
