import type { ChatRoom } from './api'

export type RoomListFilter = 'all' | 'conversation' | 'training' | 'group'
export type RoomActivityGroupId = 'today' | 'previous_7_days' | 'earlier' | 'no_activity'

export interface RoomActivityGroup {
  id: RoomActivityGroupId
  rooms: ChatRoom[]
}

export interface RoomListFilterOptions {
  query?: string
  filter?: RoomListFilter
}

const DAY_MS = 24 * 60 * 60 * 1000

function timestampFromIso(value: string | null | undefined): number {
  if (!value) return 0
  const time = new Date(value).getTime()
  return Number.isFinite(time) ? time : 0
}

export function roomActivityTime(room: ChatRoom): number {
  return Math.max(timestampFromIso(room.last_message_at), timestampFromIso(room.created_at))
}

export function sortRoomsByActivity(rooms: ChatRoom[]): ChatRoom[] {
  return [...rooms].sort((a, b) => (
    roomActivityTime(b) - roomActivityTime(a)
    || a.name.localeCompare(b.name)
    || a.id - b.id
  ))
}

export function roomMatchesFilter(room: ChatRoom, filter: RoomListFilter = 'all'): boolean {
  if (filter === 'all') return true
  if (filter === 'conversation') return room.type !== 'battle_prep'
  if (filter === 'training') return room.type === 'battle_prep'
  return room.type === 'group'
}

export function roomMatchesQuery(room: ChatRoom, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [
    room.name,
    room.type,
    ...room.persona_ids,
  ].some((value) => value.toLowerCase().includes(needle))
}

export function filterRooms(
  rooms: ChatRoom[],
  { query = '', filter = 'all' }: RoomListFilterOptions = {},
): ChatRoom[] {
  return sortRoomsByActivity(
    rooms.filter((room) => roomMatchesFilter(room, filter) && roomMatchesQuery(room, query)),
  )
}

function startOfLocalDay(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
}

function activityGroupId(activityTime: number, now: Date): RoomActivityGroupId {
  if (!activityTime) return 'no_activity'
  const todayStart = startOfLocalDay(now)
  if (activityTime >= todayStart) return 'today'
  if (activityTime >= todayStart - 7 * DAY_MS) return 'previous_7_days'
  return 'earlier'
}

export function groupRoomsByActivity(
  rooms: ChatRoom[],
  now: Date = new Date(),
): RoomActivityGroup[] {
  const groups: RoomActivityGroup[] = [
    { id: 'today', rooms: [] },
    { id: 'previous_7_days', rooms: [] },
    { id: 'earlier', rooms: [] },
    { id: 'no_activity', rooms: [] },
  ]
  const groupById = new Map(groups.map((group) => [group.id, group]))

  sortRoomsByActivity(rooms).forEach((room) => {
    groupById.get(activityGroupId(roomActivityTime(room), now))?.rooms.push(room)
  })

  return groups.filter((group) => group.rooms.length > 0)
}

export function roomFilterCount(rooms: ChatRoom[], filter: RoomListFilter): number {
  return rooms.filter((room) => roomMatchesFilter(room, filter)).length
}
