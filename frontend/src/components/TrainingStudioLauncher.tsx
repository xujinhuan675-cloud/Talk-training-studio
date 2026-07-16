import { useState } from 'react'
import {
  DIFFICULTY_OPTIONS,
  FRAMEWORK_OPTIONS,
  INTERVIEW_ROLE_PRESETS,
  INTERVIEW_SCENARIO_PRESETS,
  PRODUCT_ROLE_PRESETS,
  PRODUCT_SCENARIO_PRESETS,
  SCENARIO_OPTIONS,
  TRAINING_LEVEL_OPTIONS,
  getDefaultTrainingStudioConfig,
  type InterviewRolePreset,
  type InterviewScenarioPreset,
  type ProductRolePreset,
  type ProductScenarioPreset,
  type QuestionMix,
  type TrainingLevel,
  type TrainingScenario,
  type TrainingStudioConfig,
} from '../services/trainingStudio'
import { useI18n, type TranslationKey } from '../i18n'
import './TrainingStudioLauncher.css'

interface TrainingStudioLauncherProps {
  value: TrainingStudioConfig
  onChange: (next: TrainingStudioConfig) => void
  disabled?: boolean
}

type PresetProfileKey = 'quick' | 'standard' | 'challenge'
type ActivePreset = PresetProfileKey | 'custom'
type PresetProfile = Pick<TrainingStudioConfig, 'difficulty' | 'framework' | 'questionCount' | 'questionMix'>

const QUESTION_COUNT_OPTIONS = [5, 8, 10, 12, 15]

const PRESET_PROFILES: Record<PresetProfileKey, PresetProfile> = {
  quick: {
    difficulty: 'easy',
    framework: 'prep',
    questionCount: 5,
    questionMix: { behavioral: 50, technical: 30, pressure: 20 },
  },
  standard: {
    difficulty: 'medium',
    framework: 'star',
    questionCount: 8,
    questionMix: { behavioral: 40, technical: 35, pressure: 25 },
  },
  challenge: {
    difficulty: 'hard',
    framework: 'pyramid',
    questionCount: 12,
    questionMix: { behavioral: 25, technical: 35, pressure: 40 },
  },
}

const PRESET_PROFILE_ORDER: PresetProfileKey[] = ['quick', 'standard', 'challenge']

const LAUNCHER_PRESETS: Array<{
  value: PresetProfileKey
  labelKey: TranslationKey
  descKey: TranslationKey
}> = [
  {
    value: 'quick',
    labelKey: 'training.launcher.preset.quick.label',
    descKey: 'training.launcher.preset.quick.desc',
  },
  {
    value: 'standard',
    labelKey: 'training.launcher.preset.standard.label',
    descKey: 'training.launcher.preset.standard.desc',
  },
  {
    value: 'challenge',
    labelKey: 'training.launcher.preset.challenge.label',
    descKey: 'training.launcher.preset.challenge.desc',
  },
]

function clampPercent(value: number) {
  if (Number.isNaN(value)) return 0
  return Math.max(0, Math.min(100, value))
}

function isSameQuestionMix(a: QuestionMix, b: QuestionMix) {
  return a.behavioral === b.behavioral && a.technical === b.technical && a.pressure === b.pressure
}

function getActivePreset(value: TrainingStudioConfig): ActivePreset {
  const matched = PRESET_PROFILE_ORDER.find((preset) => {
    const profile = PRESET_PROFILES[preset]
    return (
      value.difficulty === profile.difficulty
      && value.framework === profile.framework
      && value.questionCount === profile.questionCount
      && isSameQuestionMix(value.questionMix, profile.questionMix)
    )
  })

  return matched ?? 'custom'
}

export default function TrainingStudioLauncher({
  value,
  onChange,
  disabled = false,
}: TrainingStudioLauncherProps) {
  const { t } = useI18n()
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const activePreset = getActivePreset(value)

  const update = <K extends keyof TrainingStudioConfig>(key: K, nextValue: TrainingStudioConfig[K]) => {
    onChange({ ...value, [key]: nextValue })
  }

  const updateMix = (key: keyof QuestionMix, nextValue: number) => {
    update('questionMix', {
      ...value.questionMix,
      [key]: clampPercent(nextValue),
    })
  }

  const updateScenario = (scenario: TrainingScenario) => {
    if (scenario === 'interview') {
      onChange({
        ...value,
        scenario,
        interviewRolePreset: value.interviewRolePreset || INTERVIEW_ROLE_PRESETS[1].value,
        interviewScenarioPreset: value.interviewScenarioPreset || INTERVIEW_SCENARIO_PRESETS[1].value,
        productRolePreset: '',
        productScenarioPreset: '',
      })
      return
    }

    if (scenario === 'product_management') {
      onChange({
        ...value,
        scenario,
        interviewRolePreset: '',
        interviewScenarioPreset: '',
        productRolePreset: value.productRolePreset || PRODUCT_ROLE_PRESETS[0].value,
        productScenarioPreset: value.productScenarioPreset || PRODUCT_SCENARIO_PRESETS[0].value,
      })
      return
    }

    onChange({
      ...value,
      scenario,
      interviewRolePreset: '',
      interviewScenarioPreset: '',
      productRolePreset: '',
      productScenarioPreset: '',
    })
  }

  const applyLauncherPreset = (preset: PresetProfileKey) => {
    const profile = PRESET_PROFILES[preset]
    onChange({
      ...value,
      ...profile,
      questionMix: { ...profile.questionMix },
    })
  }

  const applyInterviewRolePreset = (preset: InterviewRolePreset) => {
    const fallbackScenario = value.interviewScenarioPreset || INTERVIEW_SCENARIO_PRESETS[1].value
    onChange({
      ...value,
      scenario: 'interview',
      interviewRolePreset: preset.value,
      interviewScenarioPreset: fallbackScenario,
      productRolePreset: '',
      productScenarioPreset: '',
      role: t(preset.roleKey),
      level: preset.level,
      techStack: t(preset.focusKey),
      questionMix: { ...preset.questionMix },
    })
  }

  const applyInterviewScenarioPreset = (preset: InterviewScenarioPreset) => {
    const fallbackRole = INTERVIEW_ROLE_PRESETS.find((item) => item.value === value.interviewRolePreset)
      ?? INTERVIEW_ROLE_PRESETS[1]

    onChange({
      ...value,
      scenario: 'interview',
      interviewRolePreset: value.interviewRolePreset || fallbackRole.value,
      interviewScenarioPreset: preset.value,
      productRolePreset: '',
      productScenarioPreset: '',
      role: value.scenario === 'interview' ? value.role : t(fallbackRole.roleKey),
      level: value.scenario === 'interview' ? value.level : fallbackRole.level,
      techStack: t(preset.focusKey),
      framework: preset.framework,
      difficulty: preset.difficulty,
      questionMix: { ...preset.questionMix },
    })
  }

  const applyProductRolePreset = (preset: ProductRolePreset) => {
    const fallbackScenario = value.productScenarioPreset || PRODUCT_SCENARIO_PRESETS[0].value
    onChange({
      ...value,
      scenario: 'product_management',
      interviewRolePreset: '',
      interviewScenarioPreset: '',
      productRolePreset: preset.value,
      productScenarioPreset: fallbackScenario,
      role: t(preset.roleKey),
      level: preset.level,
      techStack: t(preset.focusKey),
      questionMix: { ...preset.questionMix },
    })
  }

  const applyProductScenarioPreset = (preset: ProductScenarioPreset) => {
    const fallbackRole = PRODUCT_ROLE_PRESETS.find((item) => item.value === value.productRolePreset)
      ?? PRODUCT_ROLE_PRESETS[0]

    onChange({
      ...value,
      scenario: 'product_management',
      interviewRolePreset: '',
      interviewScenarioPreset: '',
      productRolePreset: value.productRolePreset || fallbackRole.value,
      productScenarioPreset: preset.value,
      role: value.scenario === 'product_management' ? value.role : t(fallbackRole.roleKey),
      level: value.scenario === 'product_management' ? value.level : fallbackRole.level,
      techStack: t(preset.focusKey),
      framework: preset.framework,
      difficulty: preset.difficulty,
      questionMix: { ...preset.questionMix },
    })
  }

  const totalMix = value.questionMix.behavioral + value.questionMix.technical + value.questionMix.pressure

  return (
    <section className="tsl-panel" aria-label={t('training.launcher.aria')}>
      <div className="tsl-header">
        <div>
          <h2 className="tsl-title">{t('training.launcher.title')}</h2>
          <p className="tsl-subtitle">
            {t('training.launcher.subtitle')}
          </p>
        </div>
        <button
          className="tsl-reset"
          type="button"
          onClick={() => onChange(getDefaultTrainingStudioConfig(t))}
          disabled={disabled}
        >
          {t('training.launcher.reset')}
        </button>
      </div>

      <div className="tsl-section">
        <div className="tsl-section-heading">
          <div className="tsl-label">{t('training.launcher.presets')}</div>
          <span className={activePreset === 'custom' ? 'tsl-custom-status' : undefined}>
            {activePreset === 'custom' ? t('training.launcher.customStatus') : t('training.launcher.presetsHint')}
          </span>
        </div>
        <div className="tsl-preset-strip" role="group" aria-label={t('training.launcher.presets')}>
          {LAUNCHER_PRESETS.map((item) => (
            <button
              key={item.value}
              className={`tsl-preset-option ${activePreset === item.value ? 'selected' : ''}`}
              type="button"
              onClick={() => applyLauncherPreset(item.value)}
              disabled={disabled}
              aria-pressed={activePreset === item.value}
            >
              <span>{t(item.labelKey)}</span>
              <small>{t(item.descKey)}</small>
            </button>
          ))}
        </div>
      </div>

      <div className="tsl-section">
        <div className="tsl-label">{t('training.launcher.coreSettings')}</div>
        <div className="tsl-core-grid">
          <label className="tsl-field">
            <span>{t('training.launcher.scenario')}</span>
            <select
              value={value.scenario}
              onChange={(event) => updateScenario(event.target.value as TrainingScenario)}
              disabled={disabled}
            >
              {SCENARIO_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {t(item.labelKey)}
                </option>
              ))}
            </select>
          </label>

          <label className="tsl-field">
            <span>{t('training.launcher.difficulty')}</span>
            <select
              value={value.difficulty}
              onChange={(event) => update('difficulty', event.target.value as TrainingStudioConfig['difficulty'])}
              disabled={disabled}
            >
              {DIFFICULTY_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {t(item.labelKey)}
                </option>
              ))}
            </select>
          </label>

          <label className="tsl-field">
            <span>{t('training.launcher.level')}</span>
            <select
              value={value.level}
              onChange={(event) => update('level', event.target.value as TrainingLevel)}
              disabled={disabled}
            >
              {TRAINING_LEVEL_OPTIONS.map((level) => (
                <option key={level.value} value={level.value}>
                  {t(level.labelKey)}
                </option>
              ))}
            </select>
          </label>

          <label className="tsl-field">
            <span>{t('training.launcher.questions')}</span>
            <select
              value={value.questionCount}
              onChange={(event) => update('questionCount', Number(event.target.value))}
              disabled={disabled}
            >
              {QUESTION_COUNT_OPTIONS.map((count) => (
                <option key={count} value={count}>
                  {t('training.launcher.questionOption', { count })}
                </option>
              ))}
            </select>
          </label>

          <label className="tsl-field tsl-field--span-2">
            <span>{t('training.launcher.role')}</span>
            <input
              value={value.role}
              onChange={(event) => update('role', event.target.value)}
              placeholder={t('training.placeholder.role')}
              disabled={disabled}
            />
          </label>

          <label className="tsl-field tsl-field--span-2">
            <span>{t('training.launcher.techStack')}</span>
            <input
              value={value.techStack}
              onChange={(event) => update('techStack', event.target.value)}
              placeholder={t('training.placeholder.techStack')}
              disabled={disabled}
            />
          </label>
        </div>
      </div>

      <div className="tsl-advanced-shell">
        <button
          className="tsl-advanced-toggle"
          type="button"
          onClick={() => setAdvancedOpen((open) => !open)}
          aria-expanded={advancedOpen}
        >
          <span>
            <strong>{t('training.launcher.advancedSettings')}</strong>
            <small>{t('training.launcher.advancedSummary')}</small>
          </span>
          <em>{advancedOpen ? t('training.launcher.collapse') : t('training.launcher.expand')}</em>
        </button>

        {advancedOpen && (
          <div className="tsl-advanced-content">
            {value.scenario === 'interview' && (
              <div className="tsl-advanced-grid">
                <label className="tsl-field">
                  <span>{t('training.launcher.interviewRoles')}</span>
                  <select
                    value={value.interviewRolePreset}
                    onChange={(event) => {
                      const preset = INTERVIEW_ROLE_PRESETS.find((item) => item.value === event.target.value)
                      if (preset) applyInterviewRolePreset(preset)
                    }}
                    disabled={disabled}
                  >
                    {INTERVIEW_ROLE_PRESETS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {t(item.labelKey)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="tsl-field">
                  <span>{t('training.launcher.interviewScenarios')}</span>
                  <select
                    value={value.interviewScenarioPreset}
                    onChange={(event) => {
                      const preset = INTERVIEW_SCENARIO_PRESETS.find((item) => item.value === event.target.value)
                      if (preset) applyInterviewScenarioPreset(preset)
                    }}
                    disabled={disabled}
                  >
                    {INTERVIEW_SCENARIO_PRESETS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {t(item.labelKey)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            {value.scenario === 'product_management' && (
              <div className="tsl-advanced-grid">
                <label className="tsl-field">
                  <span>{t('training.launcher.productRoles')}</span>
                  <select
                    value={value.productRolePreset}
                    onChange={(event) => {
                      const preset = PRODUCT_ROLE_PRESETS.find((item) => item.value === event.target.value)
                      if (preset) applyProductRolePreset(preset)
                    }}
                    disabled={disabled}
                  >
                    {PRODUCT_ROLE_PRESETS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {t(item.labelKey)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="tsl-field">
                  <span>{t('training.launcher.productScenarios')}</span>
                  <select
                    value={value.productScenarioPreset}
                    onChange={(event) => {
                      const preset = PRODUCT_SCENARIO_PRESETS.find((item) => item.value === event.target.value)
                      if (preset) applyProductScenarioPreset(preset)
                    }}
                    disabled={disabled}
                  >
                    {PRODUCT_SCENARIO_PRESETS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {t(item.labelKey)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            <div className="tsl-advanced-grid">
              <label className="tsl-field">
                <span>{t('training.launcher.framework')}</span>
                <select
                  value={value.framework}
                  onChange={(event) => update('framework', event.target.value as TrainingStudioConfig['framework'])}
                  disabled={disabled}
                >
                  {FRAMEWORK_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {t(item.labelKey)}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="tsl-section">
              <div className="tsl-mix-heading">
                <div className="tsl-label">{t('training.launcher.questionMix')}</div>
                <span className={totalMix === 100 ? 'tsl-total ok' : 'tsl-total'}>
                  {t('training.launcher.total', { total: totalMix })}
                </span>
              </div>
              <div className="tsl-mix-grid">
                <label className="tsl-range">
                  <span>{t('training.launcher.behavioral')}</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                    value={value.questionMix.behavioral}
                    onChange={(event) => updateMix('behavioral', Number(event.target.value))}
                    disabled={disabled}
                  />
                  <output>{value.questionMix.behavioral}%</output>
                </label>

                <label className="tsl-range">
                  <span>{t('training.launcher.technical')}</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                    value={value.questionMix.technical}
                    onChange={(event) => updateMix('technical', Number(event.target.value))}
                    disabled={disabled}
                  />
                  <output>{value.questionMix.technical}%</output>
                </label>

                <label className="tsl-range">
                  <span>{t('training.launcher.pressure')}</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                    value={value.questionMix.pressure}
                    onChange={(event) => updateMix('pressure', Number(event.target.value))}
                    disabled={disabled}
                  />
                  <output>{value.questionMix.pressure}%</output>
                </label>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
