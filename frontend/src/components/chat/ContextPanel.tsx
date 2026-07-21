import { ChevronRight, ChevronLeft } from 'lucide-react'
import Avatar from '../Avatar'
import { Button } from '../ui/button'
import type { PersonaSummary } from '../../services/api'
import { useI18n } from '../../i18n'
import './ContextPanel.css'

export interface ContextPanelProps {
  /** Persona(s) in this room */
  personas: PersonaSummary[]
  /** Collapse state */
  collapsed: boolean
  onToggle: () => void
  /** Open emotion curve modal */
  onExpandEmotion?: () => void
}

/* Placeholder personality tags for personas (will be wired to real data later) */
const PLACEHOLDER_TAGS: Record<string, string[]> = {}

/** Map a tag string to a soft color. Deterministic based on tag text. */
function tagColor(tag: string): { bg: string; color: string } {
  const palette = [
    { bg: 'var(--green-soft)', color: 'var(--green)' },
    { bg: 'var(--blue-soft)', color: 'var(--blue)' },
    { bg: 'var(--violet-soft)', color: 'var(--violet)' },
    { bg: 'var(--amber-soft)', color: 'var(--amber)' },
    { bg: 'var(--rose-soft)', color: 'var(--rose)' },
  ]
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) | 0
  return palette[Math.abs(hash) % palette.length]
}

/** Mini bar chart for emotion trend (placeholder data) */
function EmotionMiniChart() {
  const { tr } = useI18n()
  const bars = [
    { value: 0.3, label: tr('平静', 'Calm') },
    { value: 0.6, label: tr('紧张', 'Tense') },
    { value: 0.4, label: tr('缓和', 'Easing') },
    { value: 0.8, label: tr('对抗', 'Opposed') },
    { value: 0.5, label: tr('合作', 'Cooperative') },
  ]
  const intensityColor = (v: number) => {
    if (v > 0.7) return 'var(--rose)'
    if (v > 0.5) return 'var(--amber)'
    return 'var(--green)'
  }
  return (
    <div className="ctx-emotion-chart">
      {bars.map((b, i) => (
        <div key={i} className="ctx-emotion-bar-wrapper">
          <div
            className="ctx-emotion-bar"
            style={{ height: `${b.value * 40}px`, background: intensityColor(b.value) }}
          />
          <span className="ctx-emotion-bar-label">{b.label}</span>
        </div>
      ))}
    </div>
  )
}

export default function ContextPanel({
  personas,
  collapsed,
  onToggle,
  onExpandEmotion,
}: ContextPanelProps) {
  const { tr } = useI18n()
  /* Placeholder score data -- will be replaced with real data later */
  const grade = 'B+'
  const metrics = [
    { label: tr('说服力', 'Persuasion'), value: 72 },
    { label: tr('情绪管理', 'Emotion'), value: 85 },
    { label: tr('结构化', 'Structure'), value: 68 },
    { label: tr('倾听', 'Listening'), value: 78 },
  ]
  const sessionXP = 120

  return (
    <aside className={`context-panel${collapsed ? ' collapsed' : ''}`}>
      <Button
        aria-label={collapsed ? tr('展开面板', 'Expand panel') : tr('收起面板', 'Collapse panel')}
        className="ctx-toggle"
        onClick={onToggle}
        size="icon"
        title={collapsed ? tr('展开面板', 'Expand panel') : tr('收起面板', 'Collapse panel')}
        variant="secondary"
      >
        {collapsed ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
      </Button>

      {!collapsed && (
        <div className="ctx-body">
          {/* Opponent profiles */}
          {personas.map((p) => {
            const tags = PLACEHOLDER_TAGS[p.id] || [p.role || tr('未知角色', 'Unknown role')]
            return (
              <div key={p.id} className="ctx-profile-card">
                <div className="ctx-profile-header">
                  <Avatar name={p.name} color={p.avatar_color || '#0F766E'} size={32} />
                  <span className="ctx-profile-name">{p.name}</span>
                </div>
                <div className="ctx-profile-tags">
                  {tags.map((t) => {
                    const c = tagColor(t)
                    return (
                      <span key={t} className="ctx-tag" style={{ background: c.bg, color: c.color }}>
                        {t}
                      </span>
                    )
                  })}
                </div>
              </div>
            )
          })}

          {/* Emotion trend */}
          <div className="ctx-section">
            <div className="ctx-section-title">{tr('情绪趋势', 'Emotion Trend')}</div>
            <EmotionMiniChart />
            {onExpandEmotion && (
              <Button className="ctx-link-btn" onClick={onExpandEmotion} size="sm" variant="ghost">
                {tr('查看详情 →', 'View details →')}
              </Button>
            )}
          </div>

          {/* Live score */}
          <div className="ctx-section">
            <div className="ctx-section-title">{tr('实时评分', 'Live Score')}</div>
            <div className="ctx-score-area">
              <div className="ctx-grade">{grade}</div>
              <div className="ctx-metrics-grid">
                {metrics.map((m) => (
                  <div key={m.label} className="ctx-metric">
                    <span className="ctx-metric-value">{m.value}</span>
                    <span className="ctx-metric-label">{m.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Session XP */}
          <div className="ctx-xp-card">
            <span className="ctx-xp-label">{tr('本次经验', 'Session XP')}</span>
            <span className="ctx-xp-value">+{sessionXP} XP</span>
          </div>
        </div>
      )}
    </aside>
  )
}
