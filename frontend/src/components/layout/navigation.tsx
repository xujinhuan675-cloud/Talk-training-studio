import type { ReactNode } from 'react'
import {
  ClipboardList,
  History,
  Home,
  MessageSquare,
  Settings,
  SlidersHorizontal,
  Swords,
  Trophy,
  TrendingUp,
} from 'lucide-react'
import type { TranslationKey } from '../../i18n'
import { MANAGEMENT_SYSTEM_ROLES, type SystemRole } from '../../services/auth'
import { APP_ROUTES } from '../../appRoutes'

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

export interface AppNavSection {
  id: string
  labelKey: TranslationKey
  items: readonly AppNavItem[]
}

export const desktopNavSections: AppNavSection[] = [
  {
    id: 'workspace',
    labelKey: 'nav.section.workspace',
    items: [{ to: APP_ROUTES.workbench, icon: <Home size={18} />, labelKey: 'nav.home', exact: true }],
  },
  {
    id: 'practice',
    labelKey: 'nav.section.practice',
    items: [
      {
        to: APP_ROUTES.practiceScenarios,
        icon: <ClipboardList size={18} />,
        labelKey: 'nav.scenarioTraining',
        exact: true,
      },
      {
        to: APP_ROUTES.practiceBattle,
        icon: <Swords size={18} />,
        labelKey: 'nav.battlePrep',
        exact: true,
        roles: MANAGEMENT_SYSTEM_ROLES,
      },
    ],
  },
  {
    id: 'records',
    labelKey: 'nav.section.records',
    items: [
      {
        to: APP_ROUTES.conversations,
        icon: <MessageSquare size={18} />,
        labelKey: 'nav.conversations',
        matchPrefix: APP_ROUTES.conversations,
      },
      {
        to: APP_ROUTES.reviewSessions,
        icon: <History size={18} />,
        labelKey: 'nav.review',
        matchPrefix: APP_ROUTES.review,
      },
    ],
  },
  {
    id: 'growth',
    labelKey: 'nav.section.growth',
    items: [
      { to: APP_ROUTES.growth, icon: <TrendingUp size={18} />, labelKey: 'nav.growth', exact: true },
      {
        to: APP_ROUTES.growthLeaderboard,
        icon: <Trophy size={18} />,
        labelKey: 'nav.scenarioLeaderboard',
        exact: true,
      },
    ],
  },
  {
    id: 'management',
    labelKey: 'nav.section.management',
    items: [
      {
        to: APP_ROUTES.config,
        icon: <Settings size={18} />,
        labelKey: 'nav.config',
        exact: true,
        roles: MANAGEMENT_SYSTEM_ROLES,
      },
      {
        to: APP_ROUTES.configScenarios,
        icon: <SlidersHorizontal size={18} />,
        labelKey: 'nav.scenarioConfig',
        exact: true,
        roles: MANAGEMENT_SYSTEM_ROLES,
      },
    ],
  },
]

export const desktopNavItems: AppNavItem[] = desktopNavSections.flatMap((section) => section.items)

export const mobileNavItems: AppNavItem[] = [
  { to: APP_ROUTES.workbench, icon: <Home size={20} />, labelKey: 'nav.home' },
  {
    to: APP_ROUTES.practiceScenarios,
    icon: <ClipboardList size={20} />,
    labelKey: 'nav.practice',
    elevated: true,
    matchPrefix: APP_ROUTES.practice,
  },
  {
    to: APP_ROUTES.conversations,
    icon: <MessageSquare size={20} />,
    labelKey: 'nav.conversations',
    matchPrefix: APP_ROUTES.conversations,
  },
  {
    to: APP_ROUTES.reviewSessions,
    icon: <History size={20} />,
    labelKey: 'nav.review',
    matchPrefix: APP_ROUTES.review,
  },
  { to: APP_ROUTES.growth, icon: <TrendingUp size={20} />, labelKey: 'nav.growth', matchPrefix: APP_ROUTES.growth },
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
