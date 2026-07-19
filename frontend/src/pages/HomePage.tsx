import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronRight,
  History,
  MessageSquare,
  Play,
  Settings,
  SlidersHorizontal,
  Target,
  TrendingUp,
} from 'lucide-react'
import { useAppContext } from '../contexts/AppContext'
import { useAuthContext } from '../contexts/AuthContext'
import { fetchRooms, type ChatRoom } from '../services/api'
import { MANAGEMENT_SYSTEM_ROLES } from '../services/auth'
import { useI18n, type TranslateInline } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { PageHeader, PageSection, PageShell } from '../components/ui/page'
import { Surface } from '../components/ui/surface'
import './HomePage.css'

const AVATAR_COLORS = ['#0F766E', '#334155', '#2563EB', '#475569', '#6366F1', '#0B5F59']

function getAvatarColor(id: string | number): string {
  const hash = String(id).split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}

function getInitial(name: string): string {
  return name.trim().charAt(0) || '?'
}

function timeAgo(dateStr: string | null, tr: TranslateInline): string {
  if (!dateStr) return ''
  const then = new Date(dateStr).getTime()
  if (Number.isNaN(then)) return ''
  const minutes = Math.floor((Date.now() - then) / 60000)
  if (minutes < 1) return tr('刚刚', 'Just now')
  if (minutes < 60) return tr('{count} 分钟前', '{count} min ago', { count: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return tr('{count} 小时前', '{count} hr ago', { count: hours })
  const days = Math.floor(hours / 24)
  if (days === 1) return tr('昨天', 'Yesterday')
  if (days < 30) return tr('{count} 天前', '{count} days ago', { count: days })
  return tr('{count} 个月前', '{count} months ago', { count: Math.floor(days / 30) })
}

const HomePage: React.FC = () => {
  const { personaMap } = useAppContext()
  const { hasAnySystemRole } = useAuthContext()
  const { tr, t } = useI18n()
  const [rooms, setRooms] = useState<ChatRoom[]>([])

  useEffect(() => {
    fetchRooms()
      .then((data) => {
        const sorted = data
          .filter((room) => room.type !== 'battle_prep')
          .sort((a, b) => {
            const ta = a.last_message_at ? new Date(a.last_message_at).getTime() : 0
            const tb = b.last_message_at ? new Date(b.last_message_at).getTime() : 0
            return tb - ta
          })
        setRooms(sorted)
      })
      .catch(() => {})
  }, [])

  const recentRooms = rooms.slice(0, 3)
  const latestRoom = recentRooms[0]
  const canUseManagementActions = hasAnySystemRole(MANAGEMENT_SYSTEM_ROLES)

  const quickLinks = [
    {
      to: APP_ROUTES.reviewSessions,
      icon: <History size={16} />,
      label: t('nav.review'),
    },
    {
      to: APP_ROUTES.growth,
      icon: <TrendingUp size={16} />,
      label: t('nav.growth'),
    },
    ...(canUseManagementActions
      ? [
          {
            to: APP_ROUTES.config,
            icon: <Settings size={16} />,
            label: t('nav.config'),
          },
        ]
      : []),
  ]

  return (
    <PageShell className="home-page" width="wide">
      <PageHeader
        icon={<Target size={16} />}
        eyebrow={t('nav.home')}
        title={tr('训练工作台', 'Training workbench')}
      />

      <div className="home-main-grid">
        <Surface className="home-start-panel" variant="accent" padding="lg">
          <div className="home-start-copy">
            <Badge tone="success">{tr('主流程', 'Primary flow')}</Badge>
            <h2>{t('common.startTraining')}</h2>
          </div>

          <div className="home-start-actions">
            <Button asChild variant="primary" className="home-start-button">
              <Link to={APP_ROUTES.practiceScenarios}>
                <Play size={16} />
                {t('nav.scenarioTraining')}
              </Link>
            </Button>
            {canUseManagementActions && (
              <Button asChild variant="secondary">
                <Link to={APP_ROUTES.practiceCustom}>
                  <SlidersHorizontal size={16} />
                  {t('nav.trainingStudio')}
                </Link>
              </Button>
            )}
          </div>

          {latestRoom ? (
            <Link to={APP_ROUTES.conversation(latestRoom.id)} className="home-continue-link">
              <span className="home-continue-icon" aria-hidden="true">
                <MessageSquare size={15} />
              </span>
              <span className="home-continue-copy">
                <strong>{tr('继续最近对话', 'Continue latest conversation')}</strong>
                <em>{latestRoom.name} · {timeAgo(latestRoom.last_message_at, tr) || tr('未记录时间', 'No time')}</em>
              </span>
              <ChevronRight size={15} />
            </Link>
          ) : (
            <div className="home-continue-link is-empty">
              <span className="home-continue-icon" aria-hidden="true">
                <MessageSquare size={15} />
              </span>
              <span className="home-continue-copy">
                <strong>{tr('暂无可继续对话', 'No conversation to continue')}</strong>
                <em>{tr('从训练目录开始', 'Start from the catalog')}</em>
              </span>
            </div>
          )}
        </Surface>

        <div className="home-side-stack">
          <PageSection className="home-quick-section" title={tr('训练后', 'After training')}>
            <Surface className="home-link-surface" padding="sm">
              <div className="home-link-list">
                {quickLinks.map((item) => (
                  <Link
                    key={item.to}
                    to={item.to}
                    className="home-link-item"
                    aria-label={item.label}
                  >
                    <span className="home-link-icon" aria-hidden="true">
                      {item.icon}
                    </span>
                    <span className="home-link-copy">
                      <strong>{item.label}</strong>
                    </span>
                    <ChevronRight size={15} />
                  </Link>
                ))}
              </div>
            </Surface>
          </PageSection>

          <PageSection
            className="home-recent-section"
            title={tr('最近对话', 'Recent conversations')}
            actions={(
              <Button asChild variant="ghost" size="sm">
                <Link to={APP_ROUTES.conversations}>
                  {t('nav.conversations')}
                  <ChevronRight size={14} />
                </Link>
              </Button>
            )}
          >
            <Surface className="home-recent-surface" padding="sm">
              {recentRooms.length === 0 ? (
                <div className="home-empty-block">
                  <p>{tr('暂无会话记录', 'No conversation records')}</p>
                </div>
              ) : (
                <div className="home-recent-list">
                  {recentRooms.map((room) => {
                    const firstPersonaId = room.persona_ids?.[0]
                    const persona = firstPersonaId ? personaMap[firstPersonaId] : null
                    const initial = persona ? getInitial(persona.name) : getInitial(room.name)
                    const color = persona
                      ? (persona.avatar_color || getAvatarColor(firstPersonaId))
                      : getAvatarColor(room.id)
                    return (
                      <Link key={room.id} to={APP_ROUTES.conversation(room.id)} className="home-recent-item">
                        <span className="home-recent-avatar" style={{ backgroundColor: color }}>
                          {initial}
                        </span>
                        <span className="home-recent-copy">
                          <strong>{room.name}</strong>
                          <em>{timeAgo(room.last_message_at, tr) || tr('未记录时间', 'No time')}</em>
                        </span>
                        <ChevronRight size={15} />
                      </Link>
                    )
                  })}
                </div>
              )}
            </Surface>
          </PageSection>
        </div>
      </div>
    </PageShell>
  )
}

export default HomePage
