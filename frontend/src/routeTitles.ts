import { APP_ROUTES } from './appRoutes'
import type { TranslationKey, Translate } from './i18n'

export const APP_DOCUMENT_TITLE = 'TalkWise'

const SETTINGS_TAB_TITLE_KEYS: Record<string, TranslationKey> = {
  personas: 'settings.tabs.personas',
  scenarios: 'settings.tabs.scenarios',
  organizations: 'settings.tabs.organizations',
  training: 'settings.tabs.training',
  config: 'settings.tabs.config',
}

const EXACT_ROUTE_TITLE_KEYS: Record<string, TranslationKey> = {
  [APP_ROUTES.workbench]: 'nav.home',
  [APP_ROUTES.practice]: 'nav.practice',
  [APP_ROUTES.practiceScenarios]: 'nav.scenarioTraining',
  [APP_ROUTES.practiceCustom]: 'nav.trainingStudio',
  [APP_ROUTES.practiceLiveCoach]: 'nav.liveCoach',
  [APP_ROUTES.practiceDefense]: 'nav.defensePrep',
  [APP_ROUTES.practiceBattle]: 'nav.battlePrep',
  [APP_ROUTES.conversations]: 'nav.conversations',
  [APP_ROUTES.review]: 'nav.review',
  [APP_ROUTES.reviewSessions]: 'nav.review',
  [APP_ROUTES.growth]: 'nav.growth',
  [APP_ROUTES.growthLeaderboard]: 'nav.scenarioLeaderboard',
  [APP_ROUTES.configScenarios]: 'settings.tabs.training',
  [APP_ROUTES.configPersonaNew]: 'settings.tabs.personas',
}

function normalizePathname(pathname: string): string {
  const rawPath = (pathname || APP_ROUTES.workbench).split('?')[0].split('#')[0]
  const path = rawPath.startsWith('/') ? rawPath : `/${rawPath}`
  if (path === '/') return path
  return path.replace(/\/+$/, '')
}

function getSearchParam(search: string, key: string): string | null {
  if (!search) return null
  const query = search.startsWith('?') ? search : `?${search}`
  return new URLSearchParams(query).get(key)
}

function isRouteOrDescendant(pathname: string, route: string): boolean {
  return pathname === route || pathname.startsWith(`${route}/`)
}

function getConfigRouteTitleKey(pathname: string, search: string): TranslationKey | null {
  if (pathname === APP_ROUTES.config) {
    const tab = getSearchParam(search, 'tab')
    if (!tab) return 'nav.settings'
    return SETTINGS_TAB_TITLE_KEYS[tab] ?? 'nav.settings'
  }

  if (/^\/config\/personas\/[^/]+\/edit$/.test(pathname)) return 'settings.tabs.personas'
  if (/^\/config\/persona\/[^/]+\/edit$/.test(pathname)) return 'settings.tabs.personas'
  if (isRouteOrDescendant(pathname, APP_ROUTES.config)) return 'nav.settings'
  return null
}

export function getRouteTitleKey(pathname: string, search = ''): TranslationKey {
  const normalizedPathname = normalizePathname(pathname)
  const exactTitleKey = EXACT_ROUTE_TITLE_KEYS[normalizedPathname]
  if (exactTitleKey) return exactTitleKey

  const configTitleKey = getConfigRouteTitleKey(normalizedPathname, search)
  if (configTitleKey) return configTitleKey

  if (isRouteOrDescendant(normalizedPathname, APP_ROUTES.conversations)) {
    return 'nav.conversations'
  }
  if (normalizedPathname.startsWith('/chat/')) return 'nav.conversations'
  if (isRouteOrDescendant(normalizedPathname, APP_ROUTES.review)) return 'nav.review'
  if (normalizedPathname.startsWith('/review/session/')) return 'nav.review'
  if (isRouteOrDescendant(normalizedPathname, APP_ROUTES.practice)) return 'nav.practice'

  return 'nav.home'
}

export function formatDocumentTitle(pageTitle: string): string {
  const normalizedTitle = pageTitle.trim()
  if (!normalizedTitle) return APP_DOCUMENT_TITLE
  return `${normalizedTitle} | ${APP_DOCUMENT_TITLE}`
}

export function getDocumentTitle(pathname: string, search: string, t: Translate): string {
  return formatDocumentTitle(t(getRouteTitleKey(pathname, search)))
}
