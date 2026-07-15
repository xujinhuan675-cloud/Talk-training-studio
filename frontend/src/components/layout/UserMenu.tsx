import React, { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, LogOut, UserRound } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { getUserDisplayRoleName } from '../../services/auth'
import { useI18n } from '../../i18n'
import './UserMenu.css'

const UserMenu: React.FC = () => {
  const { currentUser, users, switchUser, signOut } = useAuthContext()
  const { tr } = useI18n()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    window.addEventListener('pointerdown', handlePointerDown)
    return () => window.removeEventListener('pointerdown', handlePointerDown)
  }, [open])

  const userName = currentUser?.name ?? tr('未登录', 'Signed out')
  const roleName = currentUser ? getUserDisplayRoleName(currentUser) : tr('选择一个模拟用户', 'Choose a mock user')
  const avatarInitial = currentUser?.avatarInitial ?? '?'

  return (
    <div className="user-menu" ref={menuRef}>
      <button
        type="button"
        className="user-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="user-menu-avatar" aria-hidden="true">
          {avatarInitial}
        </span>
        <span className="user-menu-summary">
          <span className="user-menu-name">{userName}</span>
          <span className="user-menu-role">{roleName}</span>
        </span>
        <ChevronDown className="user-menu-chevron" size={15} aria-hidden="true" />
      </button>

      {open ? (
        <div className="user-menu-popover" role="menu">
          <div className="user-menu-heading">{tr('切换用户', 'Switch user')}</div>
          <div className="user-menu-options" role="group" aria-label={tr('模拟用户', 'Mock users')}>
            {users.map((user) => {
              const selected = currentUser?.id === user.id
              return (
                <button
                  key={user.id}
                  type="button"
                  className={`user-menu-option${selected ? ' selected' : ''}`}
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => {
                    switchUser(user.id)
                    setOpen(false)
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
                </button>
              )
            })}
          </div>

          <div className="user-menu-divider" />

          <button
            type="button"
            className="user-menu-action"
            role="menuitem"
            onClick={() => {
              signOut()
              setOpen(false)
            }}
          >
            {currentUser ? <LogOut size={15} aria-hidden="true" /> : <UserRound size={15} aria-hidden="true" />}
            <span>{currentUser ? tr('退出登录', 'Sign out') : tr('保持未登录', 'Stay signed out')}</span>
          </button>
        </div>
      ) : null}
    </div>
  )
}

export default UserMenu
