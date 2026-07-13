import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MessageSquare, Users, Plus, Trash2 } from 'lucide-react'
import { fetchRooms, deleteRoom, type ChatRoom } from '../services/api'
import ConfirmDialog from './layout/ConfirmDialog'
import { useI18n } from '../i18n'
import './RoomList.css'

interface RoomListProps {
  selectedRoomId: number | null
  onSelectRoom: (room: ChatRoom) => void
  onCreateRoom: () => void
  onRoomDeleted: (roomId: number) => void
  refreshKey: number
}

export default function RoomList({ selectedRoomId, onSelectRoom, onCreateRoom, onRoomDeleted, refreshKey }: RoomListProps) {
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
    if (location.pathname === `/chat/${roomId}`) return true
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
      to={`/chat/${room.id}`}
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
      <button
        className="room-delete-btn"
        onClick={(e) => handleDeleteClick(e, room)}
        title={tr('删除聊天室', 'Delete chat room')}
      >
        <Trash2 size={13} />
      </button>
    </Link>
  )

  return (
    <div className="room-list">
      <div className="sidebar-section-header">
        <span className="sidebar-section-title">{tr('聊天室', 'Chat Rooms')}</span>
        <button className="create-room-btn" onClick={onCreateRoom} title={tr('创建聊天室', 'Create chat room')}>
          <Plus size={15} />
        </button>
      </div>
      {regularRooms.length === 0 ? (
        <div className="room-empty">
          <p>{tr('还没有对话', 'No conversations yet')}</p>
          <button className="create-room-btn" onClick={onCreateRoom} style={{ margin: '8px auto 0', width: 'auto', padding: '6px 14px', height: 'auto', borderRadius: '6px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Plus size={12} /> {tr('新建聊天室', 'New Chat Room')}
          </button>
        </div>
      ) : (
        regularRooms.map(renderRoom)
      )}
      {battleRooms.length > 0 && (
        <>
          <div className="sidebar-section-header" style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
            <span className="sidebar-section-title" style={{ color: 'var(--amber)' }}>{tr('备战', 'Battle prep')}</span>
          </div>
          {battleRooms.map(renderRoom)}
        </>
      )}
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
