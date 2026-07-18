import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ChatRoom, PersonaSummary } from '../services/api'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n } from '../i18n'
import { MANAGEMENT_SYSTEM_ROLES, type SystemRole } from '../services/auth'
import { APP_ROUTES } from '../appRoutes'

export interface CommandResult {
  id: string
  type: 'room' | 'action' | 'persona'
  label: string
  description?: string
  icon?: string
  shortcut?: string
  onSelect: () => void
}

interface CommandAction extends CommandResult {
  roles?: readonly SystemRole[]
}

export interface UseCommandPaletteReturn {
  isOpen: boolean
  query: string
  results: CommandResult[]
  selectedIndex: number
  open: () => void
  close: () => void
  setQuery: (q: string) => void
}

export function useCommandPalette(
  rooms: ChatRoom[],
  personaMap: Record<string, PersonaSummary>,
): UseCommandPaletteReturn {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQueryState] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const navigate = useNavigate()
  const { t } = useI18n()
  const { hasAnySystemRole } = useAuthContext()
  const canUseManagementActions = hasAnySystemRole(MANAGEMENT_SYSTEM_ROLES)

  const setQuery = useCallback((nextQuery: string) => {
    setQueryState(nextQuery)
    setSelectedIndex(0)
  }, [])

  const open = useCallback(() => {
    setIsOpen(true)
    setQueryState('')
    setSelectedIndex(0)
  }, [])

  const close = useCallback(() => {
    setIsOpen(false)
    setQueryState('')
    setSelectedIndex(0)
  }, [])

  // Static action items
  const actions: CommandAction[] = useMemo(
    () => [
      {
        id: 'action-scenario-training',
        type: 'action' as const,
        label: t('command.action.startPractice'),
        icon: 'ClipboardList',
        onSelect: () => {
          close()
          navigate(APP_ROUTES.practiceScenarios)
        },
      },
      {
        id: 'action-training-studio',
        type: 'action' as const,
        label: t('command.action.customPractice'),
        icon: 'Dumbbell',
        roles: MANAGEMENT_SYSTEM_ROLES,
        onSelect: () => {
          close()
          navigate(APP_ROUTES.practiceCustom)
        },
      },
      {
        id: 'action-battle-prep',
        type: 'action' as const,
        label: t('command.action.battlePrep'),
        icon: 'Swords',
        shortcut: '\u2318B',
        roles: MANAGEMENT_SYSTEM_ROLES,
        onSelect: () => {
          close()
          navigate(APP_ROUTES.practiceBattle)
        },
      },
      {
        id: 'action-new-chat',
        type: 'action' as const,
        label: t('command.action.newChat'),
        icon: 'Plus',
        shortcut: '\u2318\u21E7N',
        onSelect: () => {
          close()
          navigate(APP_ROUTES.conversations)
        },
      },
      {
        id: 'action-growth',
        type: 'action' as const,
        label: t('command.action.growth'),
        icon: 'TrendingUp',
        shortcut: '\u2318G',
        onSelect: () => {
          close()
          navigate(APP_ROUTES.growth)
        },
      },
      {
        id: 'action-training-history',
        type: 'action' as const,
        label: t('command.action.trainingHistory'),
        icon: 'History',
        onSelect: () => {
          close()
          navigate(APP_ROUTES.reviewSessions)
        },
      },
      {
        id: 'action-scenario-leaderboard',
        type: 'action' as const,
        label: t('command.action.scenarioLeaderboard'),
        icon: 'Trophy',
        onSelect: () => {
          close()
          navigate(APP_ROUTES.growthLeaderboard)
        },
      },
      {
        id: 'action-scenario-config',
        type: 'action' as const,
        label: t('command.action.scenarioConfig'),
        icon: 'SlidersHorizontal',
        roles: MANAGEMENT_SYSTEM_ROLES,
        onSelect: () => {
          close()
          navigate(APP_ROUTES.configScenarios)
        },
      },
    ],
    [close, navigate, t],
  )

  // Build search results
  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    const items: CommandResult[] = []

    // Filter rooms
    const matchingRooms = q
      ? rooms.filter((r) => r.name.toLowerCase().includes(q))
      : rooms

    for (const room of matchingRooms.slice(0, 5)) {
      items.push({
        id: `room-${room.id}`,
        type: 'room',
        label: room.name,
        description:
          room.type === 'battle_prep'
            ? t('command.roomType.battlePrep')
            : room.type === 'group'
              ? t('command.roomType.group')
              : t('command.roomType.private'),
        icon: 'MessageSquare',
        onSelect: () => {
          close()
          navigate(APP_ROUTES.conversation(room.id))
        },
      })
    }

    // Filter actions
    const visibleActions = actions.filter((action) => {
      if (!action.roles) return true
      return hasAnySystemRole(action.roles)
    })
    const matchingActions = q
      ? visibleActions.filter((a) => a.label.toLowerCase().includes(q))
      : visibleActions

    items.push(...matchingActions)

    // Filter personas
    if (canUseManagementActions) {
      const personas = Object.values(personaMap)
      const matchingPersonas = q
        ? personas.filter((p) => p.name.toLowerCase().includes(q) || p.role.toLowerCase().includes(q))
        : personas

      for (const p of matchingPersonas.slice(0, 5)) {
        items.push({
          id: `persona-${p.id}`,
          type: 'persona',
          label: p.name,
          description: p.role,
          icon: 'User',
          onSelect: () => {
            close()
            navigate(APP_ROUTES.config)
          },
        })
      }
    }

    return items
  }, [query, rooms, personaMap, actions, close, navigate, t, hasAnySystemRole])

  const currentSelectedIndex = results.length > 0 ? Math.min(selectedIndex, results.length - 1) : 0

  // Global keyboard listeners
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey

      // Cmd+K / Ctrl+K -> toggle
      if (meta && e.key === 'k') {
        e.preventDefault()
        setIsOpen((prev) => {
          if (prev) {
            setQueryState('')
            setSelectedIndex(0)
            return false
          }
          setQueryState('')
          setSelectedIndex(0)
          return true
        })
        return
      }

      // Global shortcuts (only when palette is NOT open)
      if (!isOpen) {
        // Cmd+B -> battle prep
        if (meta && e.key === 'b' && canUseManagementActions) {
          e.preventDefault()
          navigate(APP_ROUTES.practiceBattle)
          return
        }
        // Cmd+Shift+N -> new chat
        if (meta && e.shiftKey && e.key === 'N') {
          e.preventDefault()
          navigate(APP_ROUTES.conversations)
          return
        }
        // Cmd+G -> growth
        if (meta && e.key === 'g') {
          e.preventDefault()
          navigate(APP_ROUTES.growth)
          return
        }
      }

      // Palette-specific keys (only when open)
      if (isOpen) {
        if (e.key === 'Escape') {
          e.preventDefault()
          close()
          return
        }
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setSelectedIndex((prev) => (prev + 1) % (results.length || 1))
          return
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          setSelectedIndex((prev) => (prev - 1 + (results.length || 1)) % (results.length || 1))
          return
        }
        if (e.key === 'Enter') {
          e.preventDefault()
          const item = results[currentSelectedIndex]
          if (item) item.onSelect()
          return
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, results, currentSelectedIndex, navigate, close, canUseManagementActions])

  return {
    isOpen,
    query,
    results,
    selectedIndex: currentSelectedIndex,
    open,
    close,
    setQuery,
  }
}
