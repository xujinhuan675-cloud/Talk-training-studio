import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Upload, FileText, ArrowLeft, Play } from 'lucide-react'
import { createDefenseSession, startDefenseSession, type DefenseSession, type PersonaSummary } from '../services/api'
import { useAppContext } from '../contexts/AppContext'
import { useI18n } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import './DefensePrepPage.css'

const SCENARIO_OPTIONS: { value: string; labelZh: string; labelEn: string; descZh: string; descEn: string }[] = [
  { value: 'performance_review', labelZh: '绩效评审', labelEn: 'Performance Review', descZh: '年度/季度绩效汇报', descEn: 'Annual or quarterly performance presentation' },
  { value: 'proposal_review', labelZh: '方案评审', labelEn: 'Proposal Review', descZh: '技术/业务方案答辩', descEn: 'Technical or business proposal defense' },
  { value: 'project_report', labelZh: '项目汇报', labelEn: 'Project Report', descZh: '项目进度与成果展示', descEn: 'Project progress and outcomes presentation' },
  { value: 'general', labelZh: '通用答辩', labelEn: 'General Defense', descZh: '自定义答辩场景', descEn: 'Custom defense scenario' },
  { value: 'interview', labelZh: '面试', labelEn: 'Interview', descZh: '上传简历/JD，模拟面试', descEn: 'Upload a resume or JD for a mock interview' },
  { value: 'probation_review', labelZh: '转正答辩', labelEn: 'Probation Review', descZh: '试用期转正述职', descEn: 'Probation-to-full-time review presentation' },
]

function initialState() {
  return {
    step: 1 as 1 | 2,
    file: null as File | null,
    selectedPersonaIds: [] as string[],
    scenarioType: '',
    loading: false,
    error: null as string | null,
    session: null as DefenseSession | null,
    submitting: false,
    dragOver: false,
  }
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export default function DefensePrepPage() {
  const navigate = useNavigate()
  const { personaMap } = useAppContext()
  const { tr, locale } = useI18n()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState(initialState)

  const {
    step,
    file,
    selectedPersonaIds,
    scenarioType,
    loading,
    error,
    session,
    submitting,
    dragOver,
  } = state

  const personas: PersonaSummary[] = Object.values(personaMap)

  // ---- File handling ----
  const handleFileChange = (f: File | null) => {
    if (f) {
      setState((s) => ({ ...s, file: f, error: null }))
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setState((s) => ({ ...s, dragOver: false }))
    const f = e.dataTransfer.files?.[0]
    if (f) handleFileChange(f)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setState((s) => ({ ...s, dragOver: true }))
  }

  const handleDragLeave = () => {
    setState((s) => ({ ...s, dragOver: false }))
  }

  // ---- Step 1: upload and create session ----
  const handleUpload = async () => {
    if (!file || selectedPersonaIds.length === 0 || !scenarioType) return
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const sess = await createDefenseSession(file, selectedPersonaIds, scenarioType)
      setState((s) => ({ ...s, loading: false, session: sess, step: 2 }))
    } catch (e: unknown) {
      setState((s) => ({ ...s, loading: false, error: getErrorMessage(e, tr('创建失败，请重试', 'Creation failed. Please try again.')) }))
    }
  }

  // ---- Step 2: start session and navigate to chat ----
  const handleStart = async () => {
    if (!session) return
    setState((s) => ({ ...s, submitting: true, error: null }))
    try {
      const updated = await startDefenseSession(session.id)
      if (updated.room_id) {
        navigate(APP_ROUTES.conversation(updated.room_id))
      } else {
        setState((s) => ({ ...s, submitting: false, error: tr('未能创建聊天房间，请重试', 'Could not create a chat room. Please try again.') }))
      }
    } catch (e: unknown) {
      setState((s) => ({ ...s, submitting: false, error: getErrorMessage(e, tr('启动失败，请重试', 'Start failed. Please try again.')) }))
    }
  }

  const selectedPersonaNames = selectedPersonaIds.map(id => personaMap[id]?.name ?? id).join(locale === 'zh' ? '、' : ', ')
  const selectedScenario = SCENARIO_OPTIONS.find((o) => o.value === scenarioType)
  const questions = session?.question_strategy?.questions ?? []

  return (
    <div className="dp-page">
      <div className="dp-container">
        {/* Back link */}
        <button className="dp-back" onClick={() => navigate(APP_ROUTES.practiceScenarios)}>
          <ArrowLeft size={16} />
          <span>{tr('返回训练目录', 'Back to training')}</span>
        </button>

        {/* Title */}
        <div className="dp-title-row">
          <FileText size={22} className="dp-title-icon" />
          <h1 className="dp-title">{tr('答辩准备', 'Defense Prep')}</h1>
        </div>

        {/* Step indicator */}
        <div className="dp-steps">
          {[1, 2].map((n) => (
            <div key={n} className="dp-step-item">
              <div className={`dp-step-dot ${step === n ? 'active' : step > n ? 'done' : ''}`}>
                {n}
              </div>
              <span className={`dp-step-label ${step === n ? 'active' : ''}`}>
                {n === 1 ? tr('上传文档', 'Upload Document') : tr('确认开始', 'Confirm Start')}
              </span>
              {n < 2 && <div className={`dp-step-line ${step > n ? 'done' : ''}`} />}
            </div>
          ))}
        </div>

        {/* ---- Step 1: Upload + Select ---- */}
        {step === 1 && (
          <div className="dp-card">

            {/* File upload */}
            <div className="dp-section-label">{tr('上传文档', 'Upload Document')}</div>
            {!file ? (
              <div
                className={`dp-upload-area ${dragOver ? 'drag-over' : ''}`}
                onClick={() => fileInputRef.current?.click()}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              >
                <Upload size={28} className="dp-upload-icon" />
                <span className="dp-upload-text">{tr('点击或拖拽上传文件', 'Click or drag to upload a file')}</span>
                <span className="dp-upload-hint">{tr('支持 PDF、Word、PPT、Markdown 等格式', 'Supports PDF, Word, PPT, Markdown, and more')}</span>
              </div>
            ) : (
              <div className="dp-file-selected">
                <FileText size={20} className="dp-file-icon" />
                <span className="dp-file-name">{file.name}</span>
                <button
                  className="dp-file-remove"
                  onClick={() => setState((s) => ({ ...s, file: null }))}
                >
                  {tr('移除', 'Remove')}
                </button>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              className="dp-file-input"
              onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
            />

            {/* Persona selection */}
            <div className="dp-section-label">{tr('选择答辩官（最多 5 位）', 'Choose Reviewers (up to 5)')}</div>
            <div className="dp-multi-select">
              {personas.map((p) => (
                <label key={p.id} className={`dp-multi-option ${selectedPersonaIds.includes(p.id) ? 'selected' : ''}`}>
                  <input
                    type="checkbox"
                    checked={selectedPersonaIds.includes(p.id)}
                    onChange={() => {
                      setState((s) => {
                        const ids = s.selectedPersonaIds.includes(p.id)
                          ? s.selectedPersonaIds.filter((x) => x !== p.id)
                          : s.selectedPersonaIds.length < 5
                            ? [...s.selectedPersonaIds, p.id]
                            : s.selectedPersonaIds
                        return { ...s, selectedPersonaIds: ids }
                      })
                    }}
                  />
                  <span className="dp-multi-option-name">{p.name}</span>
                  <span className="dp-multi-option-role">{p.role}</span>
                </label>
              ))}
            </div>

            {/* Scenario selection */}
            <div className="dp-section-label">{tr('答辩场景', 'Defense Scenario')}</div>
            <div className="dp-scenario-grid">
              {SCENARIO_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`dp-scenario-card ${scenarioType === opt.value ? 'selected' : ''}`}
                  onClick={() => setState((s) => ({ ...s, scenarioType: opt.value }))}
                >
                  <span className="dp-scenario-label">{tr(opt.labelZh, opt.labelEn)}</span>
                  <span className="dp-scenario-desc">{tr(opt.descZh, opt.descEn)}</span>
                </button>
              ))}
            </div>

            {error && <div className="dp-error">{error}</div>}

            <div className="dp-actions">
              <button
                className="dp-btn-primary"
                onClick={handleUpload}
                disabled={!file || selectedPersonaIds.length === 0 || !scenarioType || loading}
              >
                {loading ? (
                  <span className="dp-loading-inline">
                    <Loader2 size={16} className="dp-spinner" />
                    {tr('AI 正在准备...', 'AI is preparing...')}
                  </span>
                ) : (
                  <>
                    <Upload size={14} />
                    {tr('上传并准备', 'Upload and Prepare')}
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* ---- Step 2: Confirm + Start ---- */}
        {step === 2 && session && (
          <div className="dp-card">
            {/* Summary */}
            <div className="dp-summary">
              <div className="dp-summary-row">
                <span className="dp-summary-label">{tr('文档', 'Document')}</span>
                <span className="dp-summary-value">{session.document_title}</span>
              </div>
              <div className="dp-summary-row">
                <span className="dp-summary-label">{tr('答辩官', 'Reviewers')}</span>
                <span className="dp-summary-value">{selectedPersonaNames}</span>
              </div>
              <div className="dp-summary-row">
                <span className="dp-summary-label">{tr('场景', 'Scenario')}</span>
                <span className="dp-summary-value">
                  {selectedScenario ? tr(selectedScenario.labelZh, selectedScenario.labelEn) : session.scenario_type}
                </span>
              </div>
            </div>

            {/* Question preview */}
            {questions.length > 0 && (
              <>
                <div className="dp-section-label">{tr('预设问题 ({count})', 'Prepared Questions ({count})', { count: questions.length })}</div>
                <div className="dp-question-list">
                  {questions.map((q, i) => (
                    <div key={i} className="dp-question-item">
                      <span className="dp-question-index">{i + 1}</span>
                      <div className="dp-question-text">
                        {q.question}
                        <div className="dp-question-meta">
                          <span className="dp-question-badge">{q.dimension}</span>
                          <span className="dp-question-badge">{q.difficulty}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {error && <div className="dp-error">{error}</div>}

            <div className="dp-actions dp-actions--split">
              <button
                className="dp-btn-secondary"
                onClick={() => setState((s) => ({ ...s, step: 1, error: null }))}
              >
                <ArrowLeft size={14} />
                {tr('上一步', 'Previous')}
              </button>
              <button
                className="dp-btn-primary"
                onClick={handleStart}
                disabled={submitting}
              >
                {submitting ? (
                  <span className="dp-loading-inline">
                    <Loader2 size={16} className="dp-spinner" />
                    {tr('启动中...', 'Starting...')}
                  </span>
                ) : (
                  <>
                    <Play size={14} />
                    {tr('开始模拟答辩', 'Start Mock Defense')}
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
