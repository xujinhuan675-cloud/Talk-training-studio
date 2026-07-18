import type { ReactNode } from 'react'
import {
  ClipboardList,
  Dumbbell,
  History,
  Home,
  MessageSquare,
  Settings,
  TrendingUp,
  Trophy,
} from 'lucide-react'
import type { TranslationKey } from '../../i18n'
import { MANAGEMENT_SYSTEM_ROLES, type SystemRole } from '../../services/auth'

export interface AppNavItem {
  to: string
  icon: ReactNode
  labelKey: TranslationKey
  exact?: boolean
  matchPaths?: string[]
  matchPrefix?: string
  matchPrefixes?: string[]
  roles?: readonly SystemRole[]
  elevated?: boolean
}

export const desktopNavItems: AppNavItem[] = [
  { to: '/', icon: <Home size={18} />, labelKey: 'nav.home', exact: true },
  {
    to: '/scenario-training',
    icon: <ClipboardList size={18} />,
    labelKey: 'nav.scenarioTraining',
  },
  {
    to: '/training-studio',
    icon: <Dumbbell size={18} />,
    labelKey: 'nav.trainingStudio',
    matchPaths: ['/live-coach', '/battle-prep', '/defense-prep'],
    roles: MANAGEMENT_SYSTEM_ROLES,
  },
  { to: '/chat', icon: <MessageSquare size={18} />, labelKey: 'nav.chat' },
  {
    to: '/training-history',
    icon: <History size={18} />,
    labelKey: 'nav.trainingHistory',
    matchPaths: ['/training-result', '/training/history', '/training/result'],
  },
  { to: '/scenario-leaderboard', icon: <Trophy size={18} />, labelKey: 'nav.scenarioLeaderboard' },
  { to: '/growth', icon: <TrendingUp size={18} />, labelKey: 'nav.growth' },
  {
    to: '/settings',
    icon: <Settings size={18} />,
    labelKey: 'nav.settings',
    matchPaths: ['/scenario-config'],
    roles: MANAGEMENT_SYSTEM_ROLES,
  },
]

export const mobileNavItems: AppNavItem[] = [
  { to: '/', icon: <Home size={20} />, labelKey: 'nav.home' },
  {
    to: '/scenario-training',
    icon: <ClipboardList size={20} />,
    labelKey: 'nav.scenarioTrainingShort',
    elevated: true,
    matchPrefix: '/scenario-training',
    matchPrefixes: ['/training-studio', '/live-coach', '/scenario-config', '/scenario-leaderboard', '/battle-prep', '/defense-prep'],
  },
  { to: '/chat', icon: <MessageSquare size={20} />, labelKey: 'nav.chat', matchPrefix: '/chat' },
  {
    to: '/training-history',
    icon: <History size={20} />,
    labelKey: 'nav.trainingHistory',
    matchPrefix: '/training-history',
    matchPrefixes: ['/training-result', '/training/history', '/training/result'],
  },
  { to: '/growth', icon: <TrendingUp size={20} />, labelKey: 'nav.growth', matchPrefix: '/growth' },
]

export function isNavItemActive(pathname: string, item: AppNavItem): boolean {
  if (item.exact) return pathname === item.to
  if (item.matchPaths?.some((path) => pathname === path || pathname.startsWith(`${path}/`))) {
    return true
  }
  if (item.matchPrefixes?.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) {
    return true
  }
  if (item.matchPrefix) return pathname.startsWith(item.matchPrefix)
  return pathname === item.to || pathname.startsWith(`${item.to}/`)
}
