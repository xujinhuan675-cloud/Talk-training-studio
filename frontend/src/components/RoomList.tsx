import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronDown, Filter, MessageSquare, Plus, Search, Swords, Trash2, Users } from 'lucide-react'
import { fetchRooms, deleteRoom, type ChatRoom } from '../services/api'
import {
  filterRooms,
  getRoomDisplayName,
  groupRoomsByActivity,
  roomFilterCount,
  type RoomActivityGroupId,
  type RoomListFilter,
} from '../services/roomList'
import ConfirmDialog from './layout/ConfirmDialog'
import { useI18n } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { Button } from './ui/button'
import { Input, Select } from './ui/form'
import './RoomList.css'

interface RoomListProps {
  selectedRoomId: number | null
  onSelectRoom: (room: ChatRoom) => void
  onRoomDeleted: (roomId: number) => void
  refreshKey: number
}

export default function RoomList({ selectedRoomId, onSelectRoom, onRoomDeleted, refreshKey }: RoomListProps) {
  const { tr } = useI18n()
  const [loadedRefreshKey, setLoadedRefreshKey] = useState<number | null>(null)
  const [rooms, setRooms] = useState<ChatRoom[]>([])
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<RoomListFilter>('all')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<RoomActivityGroupId>>(
    () => new Set(['earlier', 'no_activity']),
  )
  const [error, setError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ChatRoom | null>(null)
  const location = useLocation()

  useEffect(() => {
    fetchRooms()
      .then((nextRooms) => {
        setRooms(nextRooms)
        setError(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : tr('加载失败', 'Failed to load')))
      .finally(() => setLoadedRefreshKey(refreshKey))
  }, [refreshKey, tr])

  const filteredRooms = useMemo(
    () => filterRooms(rooms, { query, filter }),
    [filter, query, rooms],
  )
  const groupedRooms = useMemo(
    () => groupRoomsByActivity(filteredRooms),
    [filteredRooms],
  )

  const handleDeleteClick = (e: React.MouseEvent, room: ChatRoom) => {
    e.stopPropagation()
    e.preventDefault()
    setDeleteTarget(room)
  }

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return
    try {
      await deleteRoom(deleteTarget.id)
      setRooms((prev) => prev.filter((r) => r.id !== deleteTarget.id))
      onRoomDeleted(deleteTarget.id)
    } catch (err) {
      console.error('Delete failed:', err)
    }
    setDeleteTarget(null)
  }

  const isActive = (roomId: number) => {
    if (location.pathname === APP_ROUTES.conversation(roomId)) return true
    return selectedRoomId === roomId
  }

  const groupLabel = (id: RoomActivityGroupId): string => {
    if (id === 'today') return tr('今天', 'Today')
    if (id === 'previous_7_days') return tr('近 7 天', 'Previous 7 days')
    if (id === 'earlier') return tr('更早', 'Earlier')
    return tr('无活动时间', 'No activity')
  }

  const toggleGroup = (id: RoomActivityGroupId) => {
    setCollapsedGroups((current) => {
      const next = new Set(current)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const renderControls = () => (
    <>
      <div className="sidebar-section-header room-list-top">
        <span className="sidebar-section-title room-list-title">{tr('会话', 'Conversations')}</span>
        <Button asChild variant="secondary" size="sm" className="room-list-create">
          <Link
            to={APP_ROUTES.conversations}
            title={tr('新建会话', 'New conversation')}
            aria-label={tr('新建会话', 'New conversation')}
          >
            <span>{tr('新建', 'New')}</span>
            <Plus size={13} />
          </Link>
        </Button>
      </div>

      <div className="room-list-controls" aria-label={tr('会话管理', 'Conversation management')}>
        <label className="room-list-search">
          <Search size={14} />
          <Input
            aria-label={tr('筛选当前会话列表', 'Filter current conversation list')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tr('筛选当前会话', 'Filter current conversations')}
          />
        </label>
        <label className="room-list-filter">
          <Filter size={14} />
          <Select
            aria-label={tr('会话类型', 'Conversation type')}
            value={filter}
            onChange={(event) => setFilter(event.target.value as RoomListFilter)}
          >
            <option value="all">
              {tr('全部', 'All')} ({rooms.length})
            </option>
            <option value="conversation">
              {tr('普通对话', 'Chats')} ({roomFilterCount(rooms, 'conversation')})
            </option>
            <option value="training">
              {tr('训练/备战', 'Training')} ({roomFilterCount(rooms, 'training')})
            </option>
            <option value="group">
              {tr('群聊', 'Group')} ({roomFilterCount(rooms, 'group')})
            </option>
          </Select>
        </label>
      </div>
    </>
  )

  const renderRoom = (room: ChatRoom) => (
    <Link
      key={room.id}
      to={APP_ROUTES.conversation(room.id)}
      className={`room-item ${isActive(room.id) ? 'active' : ''} ${room.type === 'battle_prep' ? 'battle-prep' : ''}`}
      onClick={() => onSelectRoom(room)}
      style={{ textDecoration: 'none', color: 'inherit' }}
    >
      <div className="room-item-icon">
        {room.type === 'battle_prep'
          ? <Swords size={16} />
          : room.type === 'private'
            ? <MessageSquare size={16} />
            : <Users size={16} />}
      </div>
      <div className="room-info">
        <span className="room-name">{getRoomDisplayName(room.name)}</span>
      </div>
      <Button
        className="room-delete-btn"
        variant="ghost"
        size="icon"
        onClick={(e) => handleDeleteClick(e, room)}
        title={tr('删除对话房间', 'Delete conversation room')}
        aria-label={tr('删除对话房间', 'Delete conversation room')}
      >
        <Trash2 size={13} />
      </Button>
    </Link>
  )

  if (loadedRefreshKey !== refreshKey) {
    return (
      <div className="room-list">
        {renderControls()}
        <span className="room-list-loading">{tr('加载中...', 'Loading...')}</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="room-list">
        {renderControls()}
        <span className="room-list-loading">{tr('加载失败', 'Failed to load')}</span>
      </div>
    )
  }

  return (
    <div className="room-list">
      {renderControls()}
      {groupedRooms.length > 0 ? (
        groupedRooms.map((group) => {
          const collapsed = collapsedGroups.has(group.id)
          const groupBodyId = `room-list-group-${group.id}`
          return (
            <section className="room-list-section" key={group.id} aria-label={groupLabel(group.id)}>
              <button
                type="button"
                className={`room-list-group-heading${collapsed ? ' collapsed' : ''}`}
                aria-expanded={!collapsed}
                aria-controls={groupBodyId}
                onClick={() => toggleGroup(group.id)}
              >
                <span>{groupLabel(group.id)}</span>
                <ChevronDown size={13} aria-hidden="true" />
              </button>
              {!collapsed && (
                <div id={groupBodyId} className="room-list-group-body">
                  {group.rooms.map(renderRoom)}
                </div>
              )}
            </section>
          )
        })
      ) : (
        <div className="room-list-empty">
          {query.trim() || filter !== 'all'
            ? tr('没有匹配的会话', 'No matching conversations')
            : tr('暂无会话', 'No conversations yet')}
        </div>
      )}
      <ConfirmDialog
        open={deleteTarget !== null}
        title={tr('删除对话', 'Delete Conversation')}
        message={tr('确定删除「{name}」？所有消息将一并删除，此操作无法撤销。', 'Delete "{name}"? All messages will be removed and this cannot be undone.', {
          name: deleteTarget?.name ?? '',
        })}
        confirmLabel={tr('删除', 'Delete')}
        cancelLabel={tr('取消', 'Cancel')}
        danger
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
