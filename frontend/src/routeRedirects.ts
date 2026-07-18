import { APP_ROUTES } from './appRoutes'

export interface RedirectLocationLike {
  search: string
  state: unknown
}

export interface RedirectTarget {
  to: string
  state: unknown
}

export function createRedirectTarget(to: string, location: RedirectLocationLike): RedirectTarget {
  return {
    to: `${to}${location.search}`,
    state: location.state,
  }
}

export function resolveConversationRoomRedirectTarget(roomId: string | number | undefined | null): string {
  return APP_ROUTES.conversation(roomId ?? '')
}

export function resolveTrainingResultSessionRedirectTarget(sessionId: string | number | undefined | null): string {
  return APP_ROUTES.reviewSession(sessionId ?? '')
}

export function resolvePersonaEditRedirectTarget(personaId: string | number | undefined | null): string {
  return APP_ROUTES.configPersonaEdit(personaId ?? '')
}
