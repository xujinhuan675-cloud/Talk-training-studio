import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Upload, FileText, ArrowLeft, Play } from 'lucide-react'
import { createDefenseSession, startDefenseSession, type DefenseSession, type PersonaSummary } from '../services/api'
import { useAppContext } from '../contexts/AppContext'
import { useI18n, type TranslationKey } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { Button } from '../components/ui/button'
import { Checkbox } from '../components/ui/checkbox'
import { Input } from '../components/ui/form'
import './DefensePrepPage.css'

interface DefenseScenarioOption {
  value: string
  labelKey: TranslationKey
  descKey: TranslationKey
}

const SCENARIO_OPTIONS: DefenseScenarioOption[] = [
  {
    value: 'performance_review',
    labelKey: 'defensePrep.scenario.performance_review.label',
    descKey: 'defensePrep.scenario.performance_review.desc',
  },
  {
    value: 'proposal_review',
    labelKey: 'defensePrep.scenario.proposal_review.label',
    descKey: 'defensePrep.scenario.proposal_review.desc',
  },
  {
    value: 'project_report',
    labelKey: 'defensePrep.scenario.project_report.label',
    descKey: 'defensePrep.scenario.project_report.desc',
  },
  {
    value: 'general',
    labelKey: 'defensePrep.scenario.general.label',
    descKey: 'defensePrep.scenario.general.desc',
  },
  {
    value: 'interview',
    labelKey: 'defensePrep.scenario.interview.label',
    descKey: 'defensePrep.scenario.interview.desc',
  },
  {
    value: 'probation_review',
    labelKey: 'defensePrep.scenario.probation_review.label',
    descKey: 'defensePrep.scenario.probation_review.desc',
  },
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
  const { t, tr, locale } = useI18n()
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
        setState((s) => ({ ...s, submitting: false, error: tr('未能创建对话房间，请重试', 'Could not create a conversation room. Please try again.') }))
      }
    } catch (e: unknown) {
      setState((s) => ({ ...s, submitting: false, error: getErrorMessage(e, tr('启动失败，请重试', 'Start failed. Please try again.')) }))
    }
  }

  const selectedPersonaNames = selectedPersonaIds.map((id) => personaMap[id]?.name ?? id).join(locale === 'zh' ? '、' : ', ')
  const selectedScenario = SCENARIO_OPTIONS.find((o) => o.value === scenarioType)
  const questions = session?.question_strategy?.questions ?? []

  return (
    <div className="dp-page">
      <div className="dp-container">
        <header className="dp-header">
          <div className="dp-heading">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="dp-back"
              onClick={() => navigate(APP_ROUTES.practiceScenarios)}
            >
              <ArrowLeft size={16} />
              <span>{t('common.backToTrainingCatalog')}</span>
            </Button>
            <div className="dp-title-row">
              <FileText size={22} className="dp-title-icon" />
              <h1 className="dp-title">{tr('答辩准备', 'Defense Prep')}</h1>
            </div>
          </div>

          <div className="dp-steps" aria-label={tr('准备流程', 'Preparation steps')}>
            {[1, 2].map((n) => (
              <div key={n} className="dp-step-item">
                <div className={`dp-step-dot ${step === n ? 'active' : step > n ? 'done' : ''}`}>
                  {n}
                </div>
                <span className={`dp-step-label ${step === n ? 'active' : ''}`}>
                  {n === 1 ? tr('准备材料', 'Prepare material') : tr('确认问题', 'Confirm questions')}
                </span>
                {n < 2 && <div className={`dp-step-line ${step > n ? 'done' : ''}`} />}
              </div>
            ))}
          </div>
        </header>

        {/* ---- Step 1: Upload + Select ---- */}
        {step === 1 && (
          <div className="dp-card">
            <div className="dp-prep-grid">
              <section className="dp-panel dp-panel--upload">
                <div className="dp-panel-header">
                  <div className="dp-section-label">{tr('训练材料', 'Practice material')}</div>
                </div>

                {!file ? (
                  <div
                    className={`dp-upload-area ${dragOver ? 'drag-over' : ''}`}
                    onClick={() => fileInputRef.current?.click()}
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                  >
                    <Upload size={24} className="dp-upload-icon" />
                    <span className="dp-upload-text">{tr('点击或拖拽上传文件', 'Click or drag to upload a file')}</span>
                    <span className="dp-upload-hint">{tr('PDF、Word、PPT、Markdown', 'PDF, Word, PPT, Markdown')}</span>
                  </div>
                ) : (
                  <div className="dp-file-selected">
                    <FileText size={20} className="dp-file-icon" />
                    <span className="dp-file-name">{file.name}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="dp-file-remove"
                      onClick={() => setState((s) => ({ ...s, file: null }))}
                    >
                      {t('common.remove')}
                    </Button>
                  </div>
                )}
                <Input
                  ref={fileInputRef}
                  type="file"
                  className="dp-file-input"
                  onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
                />
              </section>

              <section className="dp-panel dp-panel--personas">
                <div className="dp-panel-header">
                  <div className="dp-section-label">{tr('答辩官', 'Reviewers')}</div>
                  <span className="dp-count">{selectedPersonaIds.length}/5</span>
                </div>

                {personas.length > 0 ? (
                  <div className="dp-multi-select">
                    {personas.map((p) => (
                      <label key={p.id} className={`dp-multi-option ${selectedPersonaIds.includes(p.id) ? 'selected' : ''}`}>
                        <Checkbox
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
                ) : (
                  <div className="dp-empty">{tr('暂无可选答辩官', 'No reviewers available')}</div>
                )}
              </section>

              <section className="dp-panel dp-panel--scenario">
                <div className="dp-panel-header">
                  <div className="dp-section-label">{tr('答辩场景', 'Defense Scenario')}</div>
                </div>

                <div className="dp-scenario-grid">
                  {SCENARIO_OPTIONS.map((opt) => (
                    <Button
                      key={opt.value}
                      type="button"
                      variant="secondary"
                      size="sm"
                      className={`dp-scenario-card ${scenarioType === opt.value ? 'selected' : ''}`}
                      onClick={() => setState((s) => ({ ...s, scenarioType: opt.value }))}
                      aria-pressed={scenarioType === opt.value}
                      aria-label={`${t(opt.labelKey)}. ${t(opt.descKey)}`}
                      title={t(opt.descKey)}
                    >
                      <span className="dp-scenario-label">{t(opt.labelKey)}</span>
                    </Button>
                  ))}
                </div>
              </section>
            </div>

            {error && <div className="dp-error">{error}</div>}

            <div className="dp-actions">
              <Button
                type="button"
                variant="primary"
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
              </Button>
            </div>
          </div>
        )}

        {/* ---- Step 2: Confirm + Start ---- */}
        {step === 2 && session && (
          <div className="dp-card">
            <div className="dp-confirm-grid">
              <section className="dp-panel">
                <div className="dp-panel-header">
                  <div className="dp-section-label">{tr('训练设置', 'Practice setup')}</div>
                </div>

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
                      {selectedScenario ? t(selectedScenario.labelKey) : session.scenario_type}
                    </span>
                  </div>
                </div>
              </section>

              <section className="dp-panel">
                <div className="dp-panel-header">
                  <div className="dp-section-label">{tr('预设问题', 'Prepared Questions')}</div>
                  <span className="dp-count">{questions.length}</span>
                </div>

                {questions.length > 0 ? (
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
                ) : (
                  <div className="dp-empty">{tr('暂无预设问题', 'No prepared questions')}</div>
                )}
              </section>
            </div>

            {error && <div className="dp-error">{error}</div>}

            <div className="dp-actions dp-actions--split">
              <Button
                type="button"
                variant="secondary"
                className="dp-btn-secondary"
                onClick={() => setState((s) => ({ ...s, step: 1, error: null }))}
              >
                <ArrowLeft size={14} />
                {t('common.previous')}
              </Button>
              <Button
                type="button"
                variant="primary"
                className="dp-btn-primary"
                onClick={handleStart}
                disabled={submitting}
              >
                {submitting ? (
                  <span className="dp-loading-inline">
                    <Loader2 size={16} className="dp-spinner" />
                    {t('common.starting')}
                  </span>
                ) : (
                  <>
                    <Play size={14} />
                    {tr('开始模拟答辩', 'Start mock defense')}
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
