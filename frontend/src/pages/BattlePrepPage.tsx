import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Zap, ArrowLeft, ArrowRight } from 'lucide-react'
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
import { Button } from '../components/ui/button'
import { Input, Textarea } from '../components/ui/form'
import './BattlePrepPage.css'

function initialState(t: Translate) {
  return {
    step: 1 as 1 | 2,
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

  // ---- Step 2: start battle and navigate ----
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

  return (
    <div className="bpp-page">
      <div className="bpp-container">
        <header className="bpp-header">
          <div className="bpp-heading">
            <Button className="bpp-back" variant="ghost" size="sm" onClick={() => navigate(APP_ROUTES.practiceScenarios)}>
              <ArrowLeft size={16} />
              <span>{t('common.backToTrainingCatalog')}</span>
            </Button>
            <div className="bpp-title-row">
              <Zap size={22} className="bpp-title-icon" />
              <h1 className="bpp-title">{t('nav.battlePrep')}</h1>
            </div>
          </div>

          <div className="bpp-steps" aria-label={tr('准备流程', 'Preparation steps')}>
            {[1, 2].map((n) => (
              <div key={n} className="bpp-step-item">
                <div className={`bpp-step-dot ${step === n ? 'active' : step > n ? 'done' : ''}`}>
                  {n}
                </div>
                <span className={`bpp-step-label ${step === n ? 'active' : ''}`}>
                  {n === 1
                    ? tr('描述会议', 'Describe Meeting')
                    : tr('确认对手', 'Confirm opponent')}
                </span>
                {n < 2 && <div className={`bpp-step-line ${step > n ? 'done' : ''}`} />}
              </div>
            ))}
          </div>
        </header>

        {/* ---- Step 1: Describe Meeting ---- */}
        {step === 1 && (
          <div className="bpp-card">
            <div className="bpp-setup-grid">
              <label className="bpp-brief-panel">
                <span className="bpp-field-label">{tr('训练情境', 'Training brief')}</span>
                <Textarea
                  className="bpp-textarea"
                  value={description}
                  onChange={(e) => setState((s) => ({ ...s, description: e.target.value }))}
                  placeholder={tr(
                    '跟谁谈、谈什么、你的目标、对方可能的态度...',
                    'Who you will talk to, the topic, your goal, and the other side’s likely stance...',
                  )}
                  rows={6}
                  disabled={loading}
                />
                <span className="bpp-field-note">
                  {tr('至少 10 字', '10 characters minimum')}
                </span>
              </label>

              <TrainingStudioLauncher
                value={studioConfig}
                onChange={(next) => setState((s) => ({ ...s, studioConfig: next }))}
                disabled={loading}
              />
            </div>

            {error && <div className="bpp-error">{error}</div>}

            <div className="bpp-actions">
              <Button
                className="bpp-btn-primary"
                variant="primary"
                onClick={handleGenerate}
                disabled={description.trim().length < 10 || loading}
              >
                {loading ? (
                  <span className="bpp-loading-inline">
                    <Loader2 size={16} className="bpp-spinner" />
                    {tr('AI 正在分析...', 'AI is analyzing...')}
                  </span>
                ) : (
                  <>
                    {tr('生成对手', 'Generate opponent')}
                    <ArrowRight size={14} />
                  </>
                )}
              </Button>
            </div>
          </div>
        )}

        {/* ---- Step 2: Review Opponent ---- */}
        {step === 2 && prepResult && (
          <div className="bpp-card">
            <div className="bpp-review-grid">
              <section className="bpp-panel">
                <div className="bpp-panel-header">
                  <div className="bpp-section-label">{tr('对手设定', 'Opponent setup')}</div>
                </div>

                <div className="bpp-fields">
                  <label className="bpp-field">
                    <span className="bpp-field-label">{tr('角色名称', 'Persona Name')}</span>
                    <Input
                      type="text"
                      className="bpp-input"
                      value={personaName}
                      onChange={(e) => setState((s) => ({ ...s, personaName: e.target.value }))}
                    />
                  </label>
                  <label className="bpp-field">
                    <span className="bpp-field-label">{tr('职位 / 角色', 'Position / Role')}</span>
                    <Input
                      type="text"
                      className="bpp-input"
                      value={personaRole}
                      onChange={(e) => setState((s) => ({ ...s, personaRole: e.target.value }))}
                    />
                  </label>
                  <label className="bpp-field bpp-field--span-2">
                    <span className="bpp-field-label">{tr('互动风格', 'Interaction style')}</span>
                    <Textarea
                      className="bpp-textarea bpp-textarea--sm"
                      value={personaStyle}
                      onChange={(e) => setState((s) => ({ ...s, personaStyle: e.target.value }))}
                      rows={3}
                    />
                  </label>
                </div>
              </section>

              <section className="bpp-panel">
                <div className="bpp-panel-header">
                  <div className="bpp-section-label">{tr('训练点', 'Training Points')}</div>
                  <span className="bpp-count">
                    {selectedPoints.length}/{prepResult.training_points.length}
                  </span>
                </div>

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
              </section>
            </div>

            {error && <div className="bpp-error">{error}</div>}

            <div className="bpp-actions bpp-actions--split">
              <Button
                className="bpp-btn-secondary"
                variant="secondary"
                onClick={() => setState((s) => ({ ...s, step: 1, error: null }))}
              >
                <ArrowLeft size={14} />
                {t('common.previous')}
              </Button>
              <Button
                className="bpp-btn-primary"
                variant="primary"
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
                    {t('common.starting')}
                  </span>
                ) : (
                  <>
                    {t('common.startPractice')}
                    <ArrowRight size={14} />
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
