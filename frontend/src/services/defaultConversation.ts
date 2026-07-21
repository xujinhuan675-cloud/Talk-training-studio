import {
  createPersona,
  createRoom,
  fetchRooms,
  type ChatRoom,
} from './api'

const DEFAULT_PERSONA_ID_PREFIX = 'default-conversation-partner'
const DEFAULT_ROOM_NAME = 'General conversation'

let inFlightDefaultConversation: Promise<ChatRoom> | null = null
let defaultPersonaSequence = 0

function parseRoomTimestamp(value: string | null): number {
  if (!value) return 0
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : 0
}

function getRoomRecency(room: ChatRoom): number {
  return Math.max(
    parseRoomTimestamp(room.last_message_at),
    parseRoomTimestamp(room.created_at),
  )
}

function findMostRecentUsableRoom(rooms: ChatRoom[]): ChatRoom | null {
  let latestRoom: ChatRoom | null = null
  let latestRecency = -1

  for (const room of rooms) {
    if (room.type === 'battle_prep') continue
    const recency = getRoomRecency(room)
    if (!latestRoom || recency > latestRecency) {
      latestRoom = room
      latestRecency = recency
    }
  }

  return latestRoom
}

function nextDefaultPersonaId(): string {
  defaultPersonaSequence += 1
  return `${DEFAULT_PERSONA_ID_PREFIX}-${Date.now().toString(36)}-${defaultPersonaSequence}`
}

async function createDefaultPersona(): Promise<string> {
  const personaId = nextDefaultPersonaId()
  await createPersona({
    id: personaId,
    name: 'TalkWise Guide',
    role: 'Default conversation partner',
    avatar_color: '#0F766E',
    content: [
      'You are the default TalkWise conversation partner.',
      '',
      'Start with a concise, practical question and help the user turn an open conversation into a specific communication scenario.',
      '',
      'Keep replies brief, direct, and useful until the user chooses a more specific persona or training setup.',
    ].join('\n'),
    organization_id: null,
    team_id: null,
    temporary: true,
  })

  return personaId
}

export async function createDefaultConversation(): Promise<ChatRoom> {
  const personaId = await createDefaultPersona()
  return createRoom({
    name: DEFAULT_ROOM_NAME,
    type: 'private',
    persona_ids: [personaId],
  })
}

async function ensureDefaultConversationOnce(): Promise<ChatRoom> {
  const existingRoom = findMostRecentUsableRoom(await fetchRooms())
  if (existingRoom) return existingRoom
  return createDefaultConversation()
}

export async function ensureDefaultConversation(): Promise<ChatRoom> {
  if (!inFlightDefaultConversation) {
    inFlightDefaultConversation = ensureDefaultConversationOnce()
      .finally(() => {
        inFlightDefaultConversation = null
      })
  }

  return inFlightDefaultConversation
}
