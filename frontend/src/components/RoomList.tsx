import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MessageSquare, Users, Plus, Trash2 } from 'lucide-react'
import { fetchRooms, deleteRoom, type ChatRoom } from '../services/api'
import ConfirmDialog from './layout/ConfirmDialog'
import { useI18n } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { Button } from './ui/button'
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

  /** Check if a room is active by URL or by selectedRoomId prop */
  const isActive = (roomId: number) => {
    // Check URL path
    if (location.pathname === APP_ROUTES.conversation(roomId)) return true
    // Fallback to prop-based selection (for current routing setup)
    return selectedRoomId === roomId
  }

  if (loadedRefreshKey !== refreshKey) return <div className="room-list"><span className="room-list-loading">{tr('加载中...', 'Loading...')}</span></div>
  if (error) return <div className="room-list"><span className="room-list-loading">{tr('加载失败', 'Failed to load')}</span></div>

  const regularRooms = rooms.filter(r => r.type !== 'battle_prep')
  const battleRooms = rooms.filter(r => r.type === 'battle_prep')

  const renderRoom = (room: ChatRoom) => (
    <Link
      key={room.id}
      to={APP_ROUTES.conversation(room.id)}
      className={`room-item ${isActive(room.id) ? 'active' : ''} ${room.type === 'battle_prep' ? 'battle-prep' : ''}`}
      onClick={() => onSelectRoom(room)}
      style={{ textDecoration: 'none', color: 'inherit' }}
    >
      <div className="room-item-icon">
        {room.type === 'private' ? <MessageSquare size={16} /> : <Users size={16} />}
      </div>
      <div className="room-info">
        <span className="room-name">{room.name}</span>
        <span className="room-personas">
          {room.persona_ids.join(', ')}
        </span>
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

  return (
    <div className="room-list">
      <div className="sidebar-section-header room-conversation-header">
        <span className="sidebar-section-title room-conversation-title">{tr('会话', 'Conversations')}</span>
        <Button asChild variant="secondary" size="sm" className="room-conversation-create">
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
      {regularRooms.length > 0
        ? regularRooms.map(renderRoom)
        : <div className="room-list-empty">{tr('暂无会话', 'No conversations yet')}</div>}
      <div className="sidebar-section-header room-battle-header">
        <span className="sidebar-section-title room-battle-title">{tr('备战', 'Battle prep')}</span>
        <Button asChild variant="primary" size="sm" className="room-battle-create">
          <Link
            to={APP_ROUTES.practiceBattle}
            title={tr('新建备战', 'New battle prep')}
            aria-label={tr('新建备战', 'New battle prep')}
          >
            <span>{tr('新建', 'New')}</span>
            <Plus size={13} />
          </Link>
        </Button>
      </div>
      {battleRooms.map(renderRoom)}
      <ConfirmDialog
        open={deleteTarget !== null}
        title={tr('删除对话', 'Delete Conversation')}
        message={tr('确定删除「{name}」？所有消息将一并删除，此操作无法撤销。', 'Delete “{name}”? All messages will be removed and this cannot be undone.', {
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
