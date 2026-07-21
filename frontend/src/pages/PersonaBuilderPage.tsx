// input: route /config/personas/new
// output: 输入素材（1-5 段，类型 tag）+ SSE 流式进度面板 + 失败重试 + 完成 2s 自动跳转
// owner: wanhua.gu
// pos: 表示层 - persona builder 入口页 (Story 2.6 AC1-10)；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Sparkles, RotateCcw, X, ArrowRight, Users, Loader2 } from 'lucide-react'
import { usePersonaBuild } from '../hooks/usePersonaBuild'
import { useSpeakerDetection } from '../hooks/useSpeakerDetection'
import PersonaBuildProgress from '../components/PersonaBuildProgress'
import SpeakerSelector from '../components/SpeakerSelector'
import { Button } from '../components/ui/button'
import { Input, Textarea } from '../components/ui/form'
import { SegmentedControl } from '../components/ui/segmented-control'
import type { DetectedSpeaker } from '../services/api'
import { useI18n, type TranslateInline, type TranslationKey } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import './PersonaBuilderPage.css'

type SegmentType = 'chat' | 'email' | 'meeting' | 'other'
const SEGMENT_TAGS: { type: SegmentType; labelKey: TranslationKey; dotClass: string }[] = [
  { type: 'chat', labelKey: 'personaBuilder.segment.chat', dotClass: 'tag-chat' },
  { type: 'email', labelKey: 'personaBuilder.segment.email', dotClass: 'tag-email' },
  { type: 'meeting', labelKey: 'personaBuilder.segment.meeting', dotClass: 'tag-meeting' },
  { type: 'other', labelKey: 'personaBuilder.segment.other', dotClass: 'tag-other' },
]

interface Segment {
  id: string
  text: string
  type: SegmentType
}

const MAX_SEGMENTS = 5
const CHAR_LIMIT = 400_000

function newSegment(): Segment {
  return { id: Math.random().toString(36).slice(2), text: '', type: 'chat' }
}

function placeholderFor(type: SegmentType, tr: TranslateInline): string {
  switch (type) {
    case 'chat':
      return tr(
        '粘贴聊天记录，例如：\n张三 09:21\n这个方案下周必须上线\n李四 09:22\n时间太紧…',
        'Paste chat logs, for example:\nAlex 09:21\nThis plan must launch next week\nJamie 09:22\nThe timeline is too tight...',
      )
    case 'email':
      return tr('粘贴邮件正文…', 'Paste the email body...')
    case 'meeting':
      return tr('粘贴会议纪要…', 'Paste meeting notes...')
    default:
      return tr('粘贴任何相关文本…', 'Paste any relevant text...')
  }
}

type Phase = 'input' | 'speaker-select' | 'building'

export default function PersonaBuilderPage() {
  const navigate = useNavigate()
  const { t, tr } = useI18n()
  const [segments, setSegments] = useState<Segment[]>([newSegment()])
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [phase, setPhase] = useState<Phase>('input')
  const [selectedSpeakers, setSelectedSpeakers] = useState<Set<string>>(new Set())
  const [buildQueue, setBuildQueue] = useState<DetectedSpeaker[]>([])
  const [buildIndex, setBuildIndex] = useState(0)
  const buildQueueRef = useRef<DetectedSpeaker[]>([])

  const { status, events, personaId, error, start, reset } = usePersonaBuild()
  const detection = useSpeakerDetection()

  const totalChars = useMemo(
    () => segments.reduce((sum, s) => sum + s.text.length, 0),
    [segments],
  )
  const cleanedMaterials = useMemo(
    () => segments.map((s) => s.text.trim()).filter(Boolean),
    [segments],
  )
  const canSubmit =
    status !== 'running' &&
    cleanedMaterials.length > 0 &&
    totalChars <= CHAR_LIMIT

  // AC8: persist_done 后 2 秒自动跳转
  useEffect(() => {
    if (status === 'done' && personaId) {
      const t = setTimeout(() => navigate(APP_ROUTES.configPersonaEdit(personaId)), 2000)
      return () => clearTimeout(t)
    }
  }, [status, personaId, navigate])

  // AC9 (partial): 浏览器关闭/刷新时拦截。SPA 内 <Link> 切换在声明式 Routes
  // 模式下 react-router v7 没有原生 useBlocker — 此 AC 部分通过。
  useEffect(() => {
    if (status !== 'running') return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [status])

  const addSegment = () => {
    if (segments.length >= MAX_SEGMENTS) return
    setSegments((prev) => [...prev, newSegment()])
  }
  const removeSegment = (id: string) => {
    setSegments((prev) => (prev.length <= 1 ? prev : prev.filter((s) => s.id !== id)))
  }
  const updateSegment = (id: string, patch: Partial<Segment>) => {
    setSegments((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)))
  }

  // Direct build (skip detection)
  const handleStart = () => {
    if (!canSubmit) return
    setPhase('building')
    start({
      materials: cleanedMaterials,
      name: name.trim() || undefined,
      role: role.trim() || undefined,
    })
  }

  // Speaker detection flow
  const handleDetect = () => {
    if (!canSubmit) return
    detection.detect(cleanedMaterials)
  }

  // When detection finishes with exactly 1 speaker, auto-select and build
  useEffect(() => {
    if (detection.status === 'done' && detection.speakers.length > 0) {
      const t = window.setTimeout(() => {
      if (detection.speakers.length === 1) {
        // Single speaker — auto-build directly
        const sp = detection.speakers[0]
        setPhase('building')
        start({ materials: cleanedMaterials, name: sp.name, role: sp.role })
      } else {
        setPhase('speaker-select')
        setSelectedSpeakers(new Set([detection.speakers[0].name]))
      }
      }, 0)
      return () => clearTimeout(t)
    }
  }, [detection.status, detection.speakers]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleSpeaker = useCallback((name: string) => {
    setSelectedSpeakers((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }, [])

  // Start sequential builds for selected speakers
  const handleConfirmSpeakers = () => {
    const queue = detection.speakers.filter((s) => selectedSpeakers.has(s.name))
    setBuildQueue(queue)
    buildQueueRef.current = queue
    setBuildIndex(0)
    setPhase('building')
    if (queue.length > 0) {
      start({ materials: cleanedMaterials, name: queue[0].name, role: queue[0].role })
    }
  }

  // Sequential build: when one finishes, start the next
  useEffect(() => {
    const queue = buildQueueRef.current
    if (phase !== 'building' || queue.length <= 1) return
    if (status === 'done' && buildIndex < queue.length - 1) {
      const t = window.setTimeout(() => {
        const nextIdx = buildIndex + 1
        setBuildIndex(nextIdx)
        reset()
        window.setTimeout(() => {
          start({
            materials: cleanedMaterials,
            name: queue[nextIdx].name,
            role: queue[nextIdx].role,
          })
        }, 500)
      }, 0)
      return () => clearTimeout(t)
    }
  }, [status, phase, buildIndex]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSkipDetection = () => {
    setPhase('building')
    start({
      materials: cleanedMaterials,
      name: name.trim() || undefined,
      role: role.trim() || undefined,
    })
  }

  const handleRetry = () => {
    reset()
    setTimeout(() => handleStart(), 0)
  }

  const handleManualGoto = () => {
    if (personaId) navigate(APP_ROUTES.configPersonaEdit(personaId))
  }

  const handleBackToInput = () => {
    setPhase('input')
    detection.reset()
    setSelectedSpeakers(new Set())
    setBuildQueue([])
    setBuildIndex(0)
  }

  return (
    <div className="persona-builder">
      <header className="builder-header">
        <h1>{tr('从素材生成对手', 'Generate an Opponent from Materials')}</h1>
        <p>{tr('粘贴 1-5 段聊天记录 / 邮件 / 会议纪要，让 AI 在 2-3 分钟内分析出对手画像', 'Paste 1-5 chat logs, emails, or meeting notes and let AI build an opponent profile in 2-3 minutes.')}</p>
      </header>

      <div className="builder-grid">
        {/* === 左侧：素材输入 === */}
        <section className="input-pane">
          <div className="builder-meta">
            <label className="meta-field">
              <span>{tr('角色名（可选）', 'Persona Name (optional)')}</span>
              <Input
                className="meta-input"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={tr('留空让 AI 提炼', 'Leave blank for AI to infer')}
                disabled={status === 'running'}
              />
            </label>
            <label className="meta-field">
              <span>{tr('职位（可选）', 'Role (optional)')}</span>
              <Input
                className="meta-input"
                type="text"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder={tr('留空让 AI 提炼', 'Leave blank for AI to infer')}
                disabled={status === 'running'}
              />
            </label>
          </div>

          <div className="segments-list">
            {segments.map((seg, idx) => (
              <div key={seg.id} className="input-segment">
                <div className="segment-head">
                  <span className="segment-index">{tr('素材 #{index}', 'Material #{index}', { index: idx + 1 })}</span>
                  <SegmentedControl
                    ariaLabel={tr('素材段类型', 'Material type')}
                    className="segment-tags persona-builder-segment-types"
                    onValueChange={(value) => updateSegment(seg.id, { type: value })}
                    options={SEGMENT_TAGS.map((segmentTag) => ({
                      value: segmentTag.type,
                      ariaLabel: t(segmentTag.labelKey),
                      title: t(segmentTag.labelKey),
                      disabled: status === 'running',
                      label: (
                        <span className={`persona-builder-segment-label ${segmentTag.dotClass}`}>
                          <span className="persona-builder-segment-dot" aria-hidden="true" />
                          <span>{t(segmentTag.labelKey)}</span>
                        </span>
                      ),
                    }))}
                    size="sm"
                    value={seg.type}
                  />
                  {segments.length > 1 && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="segment-remove"
                      onClick={() => removeSegment(seg.id)}
                      disabled={status === 'running'}
                      title={tr('删除这段', 'Remove this segment')}
                    >
                      <X size={14} />
                    </Button>
                  )}
                </div>
                <Textarea
                  className="segment-textarea"
                  value={seg.text}
                  onChange={(e) => updateSegment(seg.id, { text: e.target.value })}
                  placeholder={placeholderFor(seg.type, tr)}
                  disabled={status === 'running'}
                  rows={6}
                />
              </div>
            ))}
          </div>

          <Button
            variant="secondary"
            size="sm"
            className="add-segment-btn"
            onClick={addSegment}
            disabled={segments.length >= MAX_SEGMENTS || status === 'running'}
          >
            <Plus size={14} />
            {tr('添加素材（{count} / {max}）', 'Add Material ({count} / {max})', {
              count: segments.length,
              max: MAX_SEGMENTS,
            })}
          </Button>

          {/* Speaker selector (shown after detection) */}
          {phase === 'speaker-select' && detection.speakers.length > 1 && (
            <SpeakerSelector
              speakers={detection.speakers}
              selected={selectedSpeakers}
              onToggle={toggleSpeaker}
              onConfirm={handleConfirmSpeakers}
              onSkip={handleSkipDetection}
              disabled={status === 'running'}
            />
          )}

          <div className="builder-footer">
            <span className={`char-count ${totalChars > CHAR_LIMIT ? 'over' : ''}`}>
              {tr('{count} / {max} 字符', '{count} / {max} characters', {
                count: totalChars.toLocaleString(),
                max: CHAR_LIMIT.toLocaleString(),
              })}
            </span>
            {status === 'error' && (
              <Button className="btn-retry retry" variant="secondary" size="sm" onClick={handleRetry}>
                <RotateCcw size={14} />
                {tr('重试', 'Retry')}
              </Button>
            )}
            {status === 'done' && personaId && (
              <Button className="btn-goto" variant="primary" size="sm" onClick={handleManualGoto}>
                {tr('查看结果', 'View Result')}
                <ArrowRight size={14} />
              </Button>
            )}
            {phase === 'speaker-select' && (
              <Button className="btn-ghost" variant="secondary" size="sm" onClick={handleBackToInput}>
                {tr('返回修改素材', 'Back to Edit Materials')}
              </Button>
            )}
            {phase === 'building' && buildQueue.length > 1 && (
              <span className="build-progress-label">
                {tr('正在构建 {index}/{total}: {name}', 'Building {index}/{total}: {name}', {
                  index: buildIndex + 1,
                  total: buildQueue.length,
                  name: buildQueue[buildIndex]?.name || '',
                })}
              </span>
            )}
            {phase === 'input' && (
              <>
                <Button
                  className="btn-detect"
                  variant="secondary"
                  size="sm"
                  onClick={handleDetect}
                  disabled={!canSubmit || detection.status === 'detecting'}
                >
                  {detection.status === 'detecting' ? (
                    <><Loader2 size={14} className="spin" /> {tr('检测中…', 'Detecting...')}</>
                  ) : (
                    <><Users size={14} /> {tr('检测人物', 'Detect People')}</>
                  )}
                </Button>
                <Button
                  className="btn-start"
                  variant="primary"
                  size="sm"
                  onClick={handleStart}
                  disabled={!canSubmit}
                >
                  <Sparkles size={14} />
                  {status === 'running' ? tr('分析中…', 'Analyzing...') : tr('开始分析', 'Start Analysis')}
                </Button>
              </>
            )}
          </div>
        </section>

        {/* === 右侧：进度面板 === */}
        <aside className="progress-pane">
          <PersonaBuildProgress events={events} status={status} error={error} />
        </aside>
      </div>

      {/* AC7: 失败 toast — 顶部固定提示条 */}
      {status === 'error' && error && (
        <div className="builder-toast">
          <X size={14} />
          <span>{tr('分析失败：{message}', 'Analysis failed: {message}', { message: error.message })}</span>
        </div>
      )}
    </div>
  )
}
