// input: messages (Message[]), personaMap (Record<string, PersonaSummary>), optional panel actions
// output: LiveEmotionPanel 可复用实时情绪面板；EmotionSidebar 旧侧栏外壳
// owner: wanhua.gu
// pos: 前端组件 - 对话界面与右侧栏共用的实时情绪可视化面板；一旦我被更新，务必更新我的开头注释以及所属文件夹的md

import { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { Maximize2, PanelRightClose } from 'lucide-react'
import type { Message, PersonaSummary } from '../services/api'
import { seriesColor } from '../utils/seriesColor'
import { useI18n } from '../i18n'
import { Button } from './ui/button'
import '../styles/panelControls.css'
import './EmotionSidebar.css'

interface LiveEmotionPanelProps {
  messages: Message[]
  personaMap: Record<string, PersonaSummary>
  onClose?: () => void
  onExpand?: () => void
  className?: string
}

interface EmotionSidebarProps {
  messages: Message[]
  personaMap: Record<string, PersonaSummary>
  onClose: () => void
  onExpand: () => void
}

interface DataPoint {
  index: number
  label: string
  [personaId: string]: number | string | null
}

interface ChartTooltipItem {
  value?: number | string | readonly (number | string)[] | null
  dataKey?: string | number | ((obj: unknown) => unknown)
  stroke?: string
  payload?: DataPoint
}

interface ChartTooltipProps {
  active?: boolean
  payload?: readonly ChartTooltipItem[]
}

export function LiveEmotionPanel({ messages, personaMap, onClose, onExpand, className }: LiveEmotionPanelProps) {
  const { tr } = useI18n()
  const { data, personaIds, latestScores } = useMemo(() => {
    const personaMsgs = messages.filter(
      (m) => m.sender_type === 'persona' && m.emotion_score != null,
    )
    if (personaMsgs.length === 0)
      return { data: [] as DataPoint[], personaIds: [] as string[], latestScores: {} as Record<string, { score: number; label: string | null; delta: number | null }> }

    const ids = new Set<string>()
    const points: DataPoint[] = []
    // Track per-persona latest and previous scores
    const perPersonaLast: Record<string, { score: number; prev: number | null; label: string | null }> = {}

    let seq = 0
    for (const msg of personaMsgs) {
      ids.add(msg.sender_id)
      seq++
      const pt: DataPoint = { index: seq, label: `#${seq}` }
      pt[msg.sender_id] = msg.emotion_score
      pt[`${msg.sender_id}_label`] = msg.emotion_label
      points.push(pt)

      const prev = perPersonaLast[msg.sender_id]?.score ?? null
      perPersonaLast[msg.sender_id] = {
        score: msg.emotion_score!,
        prev,
        label: msg.emotion_label,
      }
    }

    const pids = Array.from(ids)
    const latest: Record<string, { score: number; label: string | null; delta: number | null }> = {}
    for (const pid of pids) {
      const info = perPersonaLast[pid]
      if (info) {
        latest[pid] = {
          score: info.score,
          label: info.label,
          delta: info.prev != null ? info.score - info.prev : null,
        }
      }
    }

    return { data: points, personaIds: pids, latestScores: latest }
  }, [messages])

  const renderTooltip = ({ active, payload }: ChartTooltipProps) => {
    if (!active || !payload?.length) return null
    const items = payload.filter((p) => p.value != null && p.payload)
    if (items.length === 0) return null
    return (
      <div className="es-tooltip">
        {items.map((item) => {
          const pid = item.dataKey as string
          const persona = personaMap[pid]
          const itemPayload = item.payload!
          const label = itemPayload[`${pid}_label`] || ''
          const score = Number(item.value)
          return (
            <div key={pid} className="es-tooltip-row">
              <span className="es-tooltip-dot" style={{ background: item.stroke }} />
              <span className="es-tooltip-name">{persona?.name || pid}</span>
              <span className="es-tooltip-score">
                {score > 0 ? '+' : ''}{score}
              </span>
              {label && <span className="es-tooltip-label">{label}</span>}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <section className={`emotion-live-panel${className ? ` ${className}` : ''}`}>
      <div className="es-header">
        <h4>{tr('实时情绪', 'Live Emotion')}</h4>
        {(onExpand || onClose) && (
          <div className="es-header-actions">
            {onExpand && (
              <Button
                className="es-icon-btn panel-toggle panel-toggle--subtle"
                variant="ghost"
                size="icon"
                onClick={onExpand}
                title={tr('详细分析', 'Detailed analysis')}
                aria-label={tr('详细分析', 'Detailed analysis')}
              >
                <Maximize2 size={14} />
              </Button>
            )}
            {onClose && (
              <Button
                className="es-icon-btn panel-toggle"
                variant="ghost"
                size="icon"
                onClick={onClose}
                title={tr('关闭', 'Close')}
                aria-label={tr('关闭', 'Close')}
              >
                <PanelRightClose size={16} />
              </Button>
            )}
          </div>
        )}
      </div>

      {data.length === 0 ? (
        <div className="es-empty">{tr('发送消息后，情绪曲线将在此实时显示', 'Emotion curves will appear here after messages are sent')}</div>
      ) : (
        <>
          <div className="es-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 5, right: 12, bottom: 5, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[-5, 5]}
                  ticks={[-5, 0, 5]}
                  tick={{ fontSize: 10 }}
                  width={28}
                />
                <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="3 3" />
                <Tooltip content={renderTooltip} />
                {personaIds.map((pid) => (
                  <Line
                    key={pid}
                    type="monotone"
                    dataKey={pid}
                    stroke={seriesColor(pid)}
                    strokeWidth={2}
                    dot={{ r: 3, fill: seriesColor(pid) }}
                    activeDot={{ r: 5 }}
                    connectNulls
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Current emotion status for each persona */}
          <div className="es-status-list">
            {personaIds.map((pid) => {
              const info = latestScores[pid]
              if (!info) return null
              const persona = personaMap[pid]
              const deltaStr = info.delta != null
                ? `${info.delta > 0 ? '+' : ''}${info.delta}`
                : null
              const deltaClass = info.delta != null
                ? info.delta > 0 ? 'up' : info.delta < 0 ? 'down' : ''
                : ''
              return (
                <div key={pid} className="es-status-item">
                  <span
                    className="es-status-dot"
                    style={{ background: seriesColor(pid) }}
                  />
                  <span className="es-status-name">{persona?.name || pid}</span>
                  <span className="es-status-score">
                    {info.score > 0 ? '+' : ''}{info.score}
                  </span>
                  {deltaStr && (
                    <span className={`es-status-delta ${deltaClass}`}>
                      ({deltaStr})
                    </span>
                  )}
                  {info.label && (
                    <span className="es-status-label">{info.label}</span>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

    </section>
  )
}

export default function EmotionSidebar({ messages, personaMap, onClose, onExpand }: EmotionSidebarProps) {
  return (
    <aside className="emotion-sidebar">
      <LiveEmotionPanel
        messages={messages}
        personaMap={personaMap}
        onClose={onClose}
        onExpand={onExpand}
      />
    </aside>
  )
}
