import React from 'react'
import { Check, ChevronDown, LogOut, UserRound } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { getUserDisplayRoleName } from '../../services/auth'
import { useI18n } from '../../i18n'
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

const UserMenu: React.FC = () => {
  const { currentUser, users, switchUser, signOut } = useAuthContext()
  const { tr } = useI18n()

  const userName = currentUser?.name ?? tr('未登录', 'Signed out')
  const roleName = currentUser ? getUserDisplayRoleName(currentUser) : tr('选择一个模拟用户', 'Choose a mock user')
  const avatarInitial = currentUser?.avatarInitial ?? '?'
  const currentUserValue = currentUser?.id ?? ''

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="user-menu-trigger">
          <span className="user-menu-avatar" aria-hidden="true">
            {avatarInitial}
          </span>
          <span className="user-menu-summary">
            <span className="user-menu-name">{userName}</span>
            <span className="user-menu-role">{roleName}</span>
          </span>
          <ChevronDown className="user-menu-chevron" size={15} aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent className="user-menu-popover" align="end">
        <DropdownMenuLabel className="user-menu-heading">{tr('切换用户', 'Switch user')}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          className="user-menu-options"
          value={currentUserValue}
          aria-label={tr('模拟用户', 'Mock users')}
        >
          {users.map((user) => {
            const selected = currentUser?.id === user.id
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

        <DropdownMenuItem
          className="user-menu-action"
          onSelect={() => {
            signOut()
          }}
        >
          {currentUser ? <LogOut size={15} aria-hidden="true" /> : <UserRound size={15} aria-hidden="true" />}
          <span>{currentUser ? tr('退出登录', 'Sign out') : tr('保持未登录', 'Stay signed out')}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default UserMenu
