import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Swords,
  MessageSquare,
  Activity,
  Users,
  Check,
  ClipboardList,
  Lock,
  ChevronRight,
  FileText,
} from 'lucide-react'
import { useAppContext } from '../contexts/AppContext'
import { fetchRooms, type ChatRoom } from '../services/api'
import { useI18n, type TranslateInline } from '../i18n'
import './HomePage.css'

/* ---------- helpers ---------- */

const AVATAR_COLORS = ['#8B5226', '#1E3A5F', '#3D2E5C', '#6B4226', '#2E4A3F', '#4A3060']

function getAvatarColor(id: string | number): string {
  const hash = String(id).split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}

function getInitial(name: string): string {
  return name.charAt(0)
}

function timeAgo(dateStr: string | null, tr: TranslateInline): string {
  if (!dateStr) return ''
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  if (isNaN(then)) return ''
  const diffMs = now - then
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return tr('刚刚', 'Just now')
  if (minutes < 60) return tr('{count} 分钟前', '{count} min ago', { count: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return tr('{count} 小时前', '{count} hr ago', { count: hours })
  const days = Math.floor(hours / 24)
  if (days === 1) return tr('昨天', 'Yesterday')
  if (days < 30) return tr('{count} 天前', '{count} days ago', { count: days })
  return tr('{count} 个月前', '{count} months ago', { count: Math.floor(days / 30) })
}

/* ---------- static data ---------- */

const dailyChallenge = {
  title: '向上汇报季度成果',
  progress: 0.35,
  xp: 100,
}

interface SkillNode {
  labelZh: string
  labelEn: string
  status: 'done' | 'current' | 'locked'
}

const skillNodes: SkillNode[] = [
  { labelZh: '入门对话', labelEn: 'Conversation Basics', status: 'done' },
  { labelZh: '情绪管理', labelEn: 'Emotion Management', status: 'done' },
  { labelZh: '向上管理', labelEn: 'Managing Up', status: 'current' },
  { labelZh: '高层博弈', labelEn: 'Executive Influence', status: 'locked' },
  { labelZh: '危机处理', labelEn: 'Crisis Handling', status: 'locked' },
]

/* ---------- component ---------- */

const HomePage: React.FC = () => {
  const { personaMap, scenarios } = useAppContext()
  const { tr, t } = useI18n()
  const [rooms, setRooms] = useState<ChatRoom[]>([])

  useEffect(() => {
    fetchRooms().then((data) => {
      // Sort by last_message_at descending, filter out battle_prep rooms
      const sorted = data
        .filter((r) => r.type !== 'battle_prep')
        .sort((a, b) => {
          const ta = a.last_message_at ? new Date(a.last_message_at).getTime() : 0
          const tb = b.last_message_at ? new Date(b.last_message_at).getTime() : 0
          return tb - ta
        })
      setRooms(sorted)
    }).catch(() => {})
  }, [])

  const recentRooms = rooms.slice(0, 3)
  const personaList = Object.values(personaMap)
  const personaCount = personaList.length
  const scenarioCount = scenarios?.length ?? 0
  return (
    <div className="home-page">
      {/* 1. Daily Challenge Banner */}
      <section className="home-daily-challenge">
        <div className="home-daily-challenge-accent" />
        <div className="home-daily-challenge-body">
          <div className="home-daily-challenge-top">
            <span className="home-section-label home-section-label--green">
              {tr('每日挑战', 'Daily Challenge')}
            </span>
            <span className="home-daily-xp">+{dailyChallenge.xp} XP</span>
          </div>
          <p className="home-daily-title">{tr(dailyChallenge.title, 'Report Quarterly Results Upward')}</p>
          <div className="home-daily-progress-track">
            <div
              className="home-daily-progress-fill"
              style={{ width: `${dailyChallenge.progress * 100}%` }}
            />
          </div>
          <button className="home-daily-btn">{tr('开始挑战', 'Start Challenge')}</button>
        </div>
      </section>

      {/* 2. Quick Action Cards */}
      <section className="home-actions-grid">
        {/* Scenario Training */}
        <Link to="/scenario-training" className="home-action-card home-action-card--green">
          <div className="home-action-icon home-action-icon--green">
            <ClipboardList size={18} />
          </div>
          <div className="home-action-text">
            <span className="home-action-label home-action-label--green">
              {t('nav.scenarioTraining')}
            </span>
            <span className="home-action-title">{tr('按业务场景开练', 'Practice by Business Scenario')}</span>
            <span className="home-action-desc">
              {tr('从销售、客服、谈判卡片进入 AI 客户陪练', 'Start from sales, service, and negotiation cards with an AI customer')}
            </span>
          </div>
        </Link>

        {/* Battle Prep */}
        <Link to="/battle-prep" className="home-action-card home-action-card--amber">
          <div className="home-action-icon home-action-icon--amber">
            <Swords size={18} />
          </div>
          <div className="home-action-text">
            <span className="home-action-label home-action-label--amber">
              {t('nav.battlePrep')}
            </span>
            <span className="home-action-title">{tr('30 分钟快速演练', '30-Minute Fast Drill')}</span>
            <span className="home-action-desc">
              {tr('针对即将到来的重要会议，进行高强度模拟对练', 'Run an intensive simulation for an upcoming important meeting')}
            </span>
          </div>
        </Link>

        {/* Defense Prep */}
        <Link to="/defense-prep" className="home-action-card home-action-card--violet">
          <div className="home-action-icon home-action-icon--violet">
            <FileText size={18} />
          </div>
          <div className="home-action-text">
            <span className="home-action-label home-action-label--violet">
              {tr('答辩准备', 'Defense Prep')}
            </span>
            <span className="home-action-title">{tr('模拟答辩演练', 'Mock Defense Practice')}</span>
            <span className="home-action-desc">
              {tr('上传文档，AI 生成针对性问题并模拟答辩场景', 'Upload a document and let AI generate targeted questions for a mock defense')}
            </span>
          </div>
        </Link>

        {/* Free Practice */}
        <Link to="/chat" className="home-action-card home-action-card--green">
          <div className="home-action-icon home-action-icon--green">
            <MessageSquare size={18} />
          </div>
          <div className="home-action-text">
            <span className="home-action-label home-action-label--green">
              {tr('自由练习', 'Free Practice')}
            </span>
            <span className="home-action-title">{tr('开放式沟通模拟', 'Open Communication Simulation')}</span>
            <span className="home-action-desc">
              {tr('选择任意角色与场景，自由探索沟通策略', 'Choose any role and scenario to explore communication strategies')}
            </span>
          </div>
        </Link>

        {/* Growth */}
        <Link to="/growth" className="home-action-card home-action-card--violet">
          <div className="home-action-icon home-action-icon--violet">
            <Activity size={18} />
          </div>
          <div className="home-action-text">
            <span className="home-action-label home-action-label--violet">
              {tr('我的成长', 'My Growth')}
            </span>
            <span className="home-action-title">{tr('沟通力评分', 'Communication Score')}</span>
            <span className="home-action-desc">
              {tr('追踪你的沟通能力成长轨迹', 'Track your communication growth over time')}
            </span>
          </div>
          <div className="home-action-score-block">
            <span className="home-action-score-number">82</span>
            <span className="home-action-score-trend">{tr('+5 本周', '+5 this week')}</span>
          </div>
        </Link>

        {/* Persona Library */}
        <Link to="/settings" className="home-action-card home-action-card--neutral">
          <div className="home-action-icon home-action-icon--neutral">
            <Users size={18} />
          </div>
          <div className="home-action-text">
            <span className="home-action-label home-action-label--neutral">
              {tr('角色库', 'Persona Library')}
            </span>
            <span className="home-action-title">{tr('管理 AI 对手', 'Manage AI Opponents')}</span>
            <span className="home-action-desc">
              {tr('{personas} 个角色 · {scenarios} 个场景', '{personas} personas · {scenarios} scenarios', {
                personas: personaCount,
                scenarios: scenarioCount,
              })}
            </span>
          </div>
          <div className="home-action-avatars">
            {personaList.slice(0, 3).map((p, i) => (
              <span
                key={p.id || i}
                className="home-action-avatar-circle"
                style={{
                  backgroundColor: p.avatar_color || getAvatarColor(p.id || i),
                  zIndex: 3 - i,
                }}
              >
                {getInitial(p.name)}
              </span>
            ))}
            {personaCount > 3 && (
              <span className="home-action-avatar-more">+{personaCount - 3}</span>
            )}
          </div>
        </Link>
      </section>

      {/* 3. Recent Conversations */}
      <section className="home-recent">
        <div className="home-section-header">
          <span className="home-section-label">{tr('最近对话', 'Recent Conversations')}</span>
          <Link to="/chat" className="home-section-link">
            {tr('查看全部', 'View All')} <ChevronRight size={14} />
          </Link>
        </div>
        {recentRooms.length === 0 ? (
          <div className="home-recent-empty">
            <p>{tr('还没有对话记录', 'No conversations yet')}</p>
            <Link to="/chat" className="home-recent-empty-cta">
              {tr('开始你的第一次练习', 'Start your first practice')}
            </Link>
          </div>
        ) : (
          <div className="home-recent-row">
            {recentRooms.map((room) => {
              const firstPersonaId = room.persona_ids?.[0]
              const persona = firstPersonaId ? personaMap[firstPersonaId] : null
              const initial = persona ? getInitial(persona.name) : getInitial(room.name)
              const color = persona
                ? (persona.avatar_color || getAvatarColor(firstPersonaId))
                : getAvatarColor(room.id)
              return (
                <Link
                  key={room.id}
                  to={`/chat/${room.id}`}
                  className="home-recent-card"
                >
                  <span
                    className="home-recent-avatar"
                    style={{ backgroundColor: color }}
                  >
                    {initial}
                  </span>
                  <div className="home-recent-info">
                    <span className="home-recent-name">{room.name}</span>
                    <span className="home-recent-time">{timeAgo(room.last_message_at, tr)}</span>
                  </div>
                </Link>
              )
            })}
          </div>
        )}
      </section>

      {/* 4. Skill Path Preview */}
      <section className="home-skill-path">
        <div className="home-section-header">
          <span className="home-section-label">{tr('技能路径', 'Skill Path')}</span>
          <Link to="/growth" className="home-section-link">
            {tr('展开', 'Expand')} <ChevronRight size={14} />
          </Link>
        </div>
        <div className="home-skill-chain">
          {skillNodes.map((node, idx) => (
            <React.Fragment key={node.labelZh}>
              {idx > 0 && <span className="home-skill-line" />}
              <div className={`home-skill-node home-skill-node--${node.status}`}>
                <span className="home-skill-circle">
                  {node.status === 'done' && <Check size={14} />}
                  {node.status === 'locked' && <Lock size={12} />}
                  {node.status === 'current' && (
                    <span className="home-skill-dot" />
                  )}
                </span>
                <span className="home-skill-label">{tr(node.labelZh, node.labelEn)}</span>
              </div>
            </React.Fragment>
          ))}
        </div>
      </section>
    </div>
  )
}

export default HomePage
