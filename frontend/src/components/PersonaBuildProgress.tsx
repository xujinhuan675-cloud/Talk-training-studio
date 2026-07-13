// input: events (BuildEvent[]), status (BuildStatus), error (BuildErrorInfo | null)
// output: 渲染 Claude Code 风格的事件 pill 流；自动滚到底部；显示 spinner 当 in-progress
// owner: wanhua.gu
// pos: 表示层 - persona build 进度面板组件 (Variant B pill UX)；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
import { useEffect, useRef } from 'react'
import {
  Check,
  X,
  Loader2,
  Sparkles,
  FileSearch,
  MessageSquare,
  Brain,
  Shield,
  Database,
} from 'lucide-react'
import type { BuildEvent } from '../services/api'
import type { BuildStatus, BuildErrorInfo } from '../hooks/usePersonaBuild'
import { useI18n, type TranslateInline } from '../i18n'
import './PersonaBuildProgress.css'

interface Props {
  events: BuildEvent[]
  status: BuildStatus
  error: BuildErrorInfo | null
}

interface RenderRow {
  key: string
  state: 'in-progress' | 'done' | 'error'
  icon: React.ReactNode
  label: string
}

const TOOL_LABELS: Record<string, { zh: string; en: string }> = {
  Read: { zh: '读取素材', en: 'Read Materials' },
  Glob: { zh: '搜索文件', en: 'Search Files' },
  Grep: { zh: '检索内容', en: 'Search Content' },
  Write: { zh: '写出画像', en: 'Write Profile' },
  Bash: { zh: '执行命令', en: 'Run Command' },
  Edit: { zh: '修改文件', en: 'Edit File' },
}

function buildRows(events: BuildEvent[], status: BuildStatus, tr: TranslateInline): RenderRow[] {
  // Drop heartbeats — they only keep the connection alive
  const filtered = events.filter((e) => e.type !== 'heartbeat')
  const rows: RenderRow[] = []

  for (const ev of filtered) {
    switch (ev.type) {
      case 'workspace_ready':
        rows.push({
          key: `${ev.seq}`,
          state: 'done',
          icon: <Sparkles size={14} />,
          label: tr('工作区就绪', 'Workspace Ready'),
        })
        break
      case 'agent_tool_use': {
        const phase = (ev.data as { phase?: string })?.phase
        const tools = (ev.data?.tool_uses as Array<{ name: string }>) || []
        const toolDesc = tools.map((t) => {
          const label = TOOL_LABELS[t.name]
          return label ? tr(label.zh, label.en) : t.name
        }).join(' · ')
        rows.push({
          key: `${ev.seq}`,
          state: 'done',
          icon: <FileSearch size={14} />,
          label: phase || tr('Agent 工具调用：{toolDesc}', 'Agent tool call: {toolDesc}', {
            toolDesc: toolDesc || '(unknown)',
          }),
        })
        break
      }
      case 'agent_message': {
        const summary = (ev.data as { summary?: string })?.summary || tr('Agent 思考', 'Agent thinking')
        rows.push({
          key: `${ev.seq}`,
          state: 'done',
          icon: <MessageSquare size={14} />,
          label: summary,
        })
        break
      }
      case 'parse_done':
        rows.push({
          key: `${ev.seq}`,
          state: 'done',
          icon: <Brain size={14} />,
          label: tr('5-layer 解析完成', '5-layer parsing complete'),
        })
        break
      case 'adversarialize_start':
        rows.push({
          key: `${ev.seq}`,
          state: 'in-progress',
          icon: <Shield size={14} />,
          label: tr('对抗化注入中…', 'Injecting adversarial behavior...'),
        })
        break
      case 'adversarialize_done': {
        // Demote previous adversarialize_start row → done
        for (let i = rows.length - 1; i >= 0; i--) {
          if (rows[i].label.includes('对抗化') || rows[i].label.includes('adversarial')) {
            rows[i] = { ...rows[i], state: 'done' }
            break
          }
        }
        const applied = (ev.data as { hostile_applied?: boolean })?.hostile_applied
        rows.push({
          key: `${ev.seq}`,
          state: 'done',
          icon: <Shield size={14} />,
          label: applied
            ? tr('对抗化注入完成', 'Adversarial behavior injected')
            : tr('对抗化降级（保留基础画像）', 'Adversarial behavior downgraded; base profile kept'),
        })
        break
      }
      case 'enhancement_start':
        rows.push({
          key: `${ev.seq}`,
          state: 'done',
          icon: <Sparkles size={14} />,
          label: tr('加载已有画像', 'Loading existing profile'),
        })
        break
      case 'enhancement_merge':
        rows.push({
          key: `${ev.seq}`,
          state: 'done',
          icon: <Database size={14} />,
          label: tr('合并新旧证据 ({count} 条)', 'Merging old and new evidence ({count})', {
            count: (ev.data as { merged_evidence_count?: number })?.merged_evidence_count || '?',
          }),
        })
        break
      case 'persist_done':
        rows.push({
          key: `${ev.seq}`,
          state: 'done',
          icon: <Database size={14} />,
          label: tr('画像已入库 ✓', 'Profile saved ✓'),
        })
        break
      case 'error':
        rows.push({
          key: `${ev.seq}`,
          state: 'error',
          icon: <X size={14} />,
          label: tr('失败', 'Failed'),
        })
        break
    }
  }

  // Synthetic "thinking" row while running and last row is settled
  if (
    status === 'running' &&
    (rows.length === 0 || rows[rows.length - 1].state === 'done')
  ) {
    rows.push({
      key: 'tail-progress',
      state: 'in-progress',
      icon: <Loader2 size={14} className="spin" />,
      label: tr('分析中…', 'Analyzing...'),
    })
  }

  return rows
}

export default function PersonaBuildProgress({ events, status, error }: Props) {
  const { tr } = useI18n()
  const rows = buildRows(events, status, tr)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new event
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [rows.length])

  if (status === 'idle' && rows.length === 0) {
    return (
      <div className="progress-empty">
        <div className="progress-empty-emoji">✨</div>
        <h3>{tr('粘贴素材后开始分析', 'Paste materials to start analysis')}</h3>
        <p>{tr('左侧粘贴聊天记录、邮件或会议纪要，点 "开始分析" 即可看到 AI 工作过程', 'Paste chat logs, emails, or meeting notes on the left, then click “Start Analysis” to watch the AI process.')}</p>
      </div>
    )
  }

  return (
    <div className="progress-pane-inner" ref={scrollRef}>
      {rows.map((r) => (
        <div
          key={r.key}
          className={`progress-event event-row ${
            r.state === 'in-progress' ? 'in-progress' : ''
          } ${r.state === 'done' ? 'done' : ''} ${
            r.state === 'error' ? 'failed' : ''
          }`}
        >
          <span className="event-icon">
            {r.state === 'done' ? <Check size={14} /> : r.icon}
          </span>
          <span className="event-label">{r.label}</span>
        </div>
      ))}
      {status === 'error' && error && (
        <div className="progress-error-banner">
          <X size={14} />
          <span>{error.message}</span>
        </div>
      )}
    </div>
  )
}
