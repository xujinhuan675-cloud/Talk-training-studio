import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Zap, ArrowLeft } from 'lucide-react'
import TrainingStudioLauncher from '../components/TrainingStudioLauncher'
import { generateBattlePrep, startBattle, type BattlePrepResult } from '../services/api'
import {
  buildTrainingStudioPrompt,
  getDefaultTrainingStudioConfig,
  toBattleDifficulty,
  type TrainingStudioConfig,
} from '../services/trainingStudio'
import { useI18n, type Translate } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import './BattlePrepPage.css'

function initialState(t: Translate) {
  return {
    step: 1 as 1 | 2 | 3,
    description: '',
    studioConfig: getDefaultTrainingStudioConfig(t) as TrainingStudioConfig,
    loading: false,
    error: null as string | null,
    prepResult: null as BattlePrepResult | null,
    personaName: '',
    personaRole: '',
    personaStyle: '',
    selectedPoints: [] as string[],
    submitting: false,
  }
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export default function BattlePrepPage() {
  const navigate = useNavigate()
  const { t, tr } = useI18n()
  const [state, setState] = useState(() => initialState(t))

  const {
    step,
    description,
    studioConfig,
    loading,
    error,
    prepResult,
    personaName,
    personaRole,
    personaStyle,
    selectedPoints,
    submitting,
  } = state

  // ---- Step 1: generate persona ----
  const handleGenerate = async () => {
    if (description.trim().length < 10) return
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const result = await generateBattlePrep(buildTrainingStudioPrompt(studioConfig, description, t))
      setState((s) => ({
        ...s,
        loading: false,
        prepResult: result,
        personaName: result.persona_name,
        personaRole: result.persona_role,
        personaStyle: result.persona_style,
        selectedPoints: [...result.training_points],
        step: 2,
      }))
    } catch (e: unknown) {
      setState((s) => ({ ...s, loading: false, error: getErrorMessage(e, tr('生成失败，请重试', 'Generation failed. Please try again.')) }))
    }
  }

  // ---- Step 2 -> Step 3: start battle and navigate ----
  const handleStartBattle = async () => {
    if (selectedPoints.length === 0 || !prepResult) return
    setState((s) => ({ ...s, submitting: true, error: null }))
    try {
      const room = await startBattle({
        persona_name: personaName,
        persona_role: personaRole,
        persona_style: personaStyle,
        scenario_context: buildTrainingStudioPrompt(studioConfig, prepResult.scenario_context, t),
        selected_training_points: selectedPoints,
        difficulty: toBattleDifficulty(studioConfig.difficulty),
      })
      navigate(APP_ROUTES.conversation(room.id))
    } catch (e: unknown) {
      setState((s) => ({ ...s, submitting: false, error: getErrorMessage(e, tr('启动失败，请重试', 'Start failed. Please try again.')) }))
    }
  }

  const togglePoint = (point: string) => {
    setState((s) => ({
      ...s,
      selectedPoints: s.selectedPoints.includes(point)
        ? s.selectedPoints.filter((p) => p !== point)
        : [...s.selectedPoints, point],
    }))
  }

  const personaInitial = personaName ? personaName.charAt(0).toUpperCase() : '?'

  return (
    <div className="bpp-page">
      <div className="bpp-container">
        {/* Back link */}
        <button className="bpp-back" onClick={() => navigate(APP_ROUTES.practiceScenarios)}>
          <ArrowLeft size={16} />
          <span>{tr('返回训练目录', 'Back to training')}</span>
        </button>

        {/* Title */}
        <div className="bpp-title-row">
          <Zap size={22} className="bpp-title-icon" />
          <h1 className="bpp-title">{t('nav.battlePrep')}</h1>
        </div>

        {/* Step indicator */}
        <div className="bpp-steps">
          {[1, 2, 3].map((n) => (
            <div key={n} className="bpp-step-item">
              <div className={`bpp-step-dot ${step === n ? 'active' : step > n ? 'done' : ''}`}>
                {n}
              </div>
              <span className={`bpp-step-label ${step === n ? 'active' : ''}`}>
                {n === 1
                  ? tr('描述会议', 'Describe Meeting')
                  : n === 2
                    ? tr('预览对手', 'Preview Opponent')
                    : tr('开始练习', 'Start Practice')}
              </span>
              {n < 3 && <div className={`bpp-step-line ${step > n ? 'done' : ''}`} />}
            </div>
          ))}
        </div>

        {/* ---- Step 1: Describe Meeting ---- */}
        {step === 1 && (
          <div className="bpp-card">

            <textarea
              className="bpp-textarea"
              value={description}
              onChange={(e) => setState((s) => ({ ...s, description: e.target.value }))}
              placeholder={tr(
                '描述你即将参加的会议：跟谁谈、谈什么、你的目标是什么、对方可能的态度...',
                'Describe the meeting: who you will talk to, the topic, your goal, and the other side’s likely stance...',
              )}
              rows={6}
              disabled={loading}
            />

            <TrainingStudioLauncher
              value={studioConfig}
              onChange={(next) => setState((s) => ({ ...s, studioConfig: next }))}
              disabled={loading}
            />

            {error && <div className="bpp-error">{error}</div>}

            <div className="bpp-actions">
              <button
                className="bpp-btn-primary"
                onClick={handleGenerate}
                disabled={description.trim().length < 10 || loading}
              >
                {loading ? (
                  <span className="bpp-loading-inline">
                    <Loader2 size={16} className="bpp-spinner" />
                    {tr('AI 正在分析...', 'AI is analyzing...')}
                  </span>
                ) : (
                  tr('生成对手 →', 'Generate Opponent →')
                )}
              </button>
            </div>
          </div>
        )}

        {/* ---- Step 2: Review Opponent ---- */}
        {step === 2 && prepResult && (
          <div className="bpp-card">
            {/* Persona preview */}
            <div className="bpp-persona-preview">
              <div className="bpp-persona-avatar">{personaInitial}</div>
              <div className="bpp-persona-meta">
                <span className="bpp-persona-name-display">{personaName || tr('未命名', 'Unnamed')}</span>
                <span className="bpp-persona-role-display">{personaRole || tr('未知角色', 'Unknown role')}</span>
              </div>
            </div>

            {/* Editable fields */}
            <div className="bpp-fields">
              <label className="bpp-field">
                <span className="bpp-field-label">{tr('角色名称', 'Persona Name')}</span>
                <input
                  type="text"
                  className="bpp-input"
                  value={personaName}
                  onChange={(e) => setState((s) => ({ ...s, personaName: e.target.value }))}
                />
              </label>
              <label className="bpp-field">
                <span className="bpp-field-label">{tr('职位 / 角色', 'Position / Role')}</span>
                <input
                  type="text"
                  className="bpp-input"
                  value={personaRole}
                  onChange={(e) => setState((s) => ({ ...s, personaRole: e.target.value }))}
                />
              </label>
              <label className="bpp-field">
                <span className="bpp-field-label">{tr('谈判风格', 'Negotiation Style')}</span>
                <textarea
                  className="bpp-textarea bpp-textarea--sm"
                  value={personaStyle}
                  onChange={(e) => setState((s) => ({ ...s, personaStyle: e.target.value }))}
                  rows={3}
                />
              </label>
            </div>

            {/* Training points */}
            <div className="bpp-section-label">{tr('训练点（至少选 1 个）', 'Training Points (choose at least 1)')}</div>
            <div className="bpp-training-list">
              {prepResult.training_points.map((point) => (
                <label key={point} className={`bpp-training-item ${selectedPoints.includes(point) ? 'checked' : ''}`}>
                  <input
                    type="checkbox"
                    checked={selectedPoints.includes(point)}
                    onChange={() => togglePoint(point)}
                  />
                  <span>{point}</span>
                </label>
              ))}
            </div>

            {error && <div className="bpp-error">{error}</div>}

            <div className="bpp-actions bpp-actions--split">
              <button
                className="bpp-btn-secondary"
                onClick={() => setState((s) => ({ ...s, step: 1, error: null }))}
              >
                <ArrowLeft size={14} />
                {tr('上一步', 'Previous')}
              </button>
              <button
                className="bpp-btn-primary"
                onClick={handleStartBattle}
                disabled={
                  !personaName.trim() ||
                  !personaRole.trim() ||
                  selectedPoints.length === 0 ||
                  submitting
                }
              >
                {submitting ? (
                  <span className="bpp-loading-inline">
                    <Loader2 size={16} className="bpp-spinner" />
                    {tr('启动中...', 'Starting...')}
                  </span>
                ) : (
                  tr('开始练习 →', 'Start Practice →')
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
