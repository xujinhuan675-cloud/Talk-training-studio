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
  type QuestionMix,
  type ProductRolePreset,
  type ProductScenarioPreset,
  type TrainingLevel,
  type TrainingScenario,
  type TrainingStudioConfig,
} from '../services/trainingStudio'
import { useI18n } from '../i18n'
import './TrainingStudioLauncher.css'

interface TrainingStudioLauncherProps {
  value: TrainingStudioConfig
  onChange: (next: TrainingStudioConfig) => void
  disabled?: boolean
}

const QUESTION_COUNT_OPTIONS = [5, 8, 10, 12, 15]

function clampPercent(value: number) {
  if (Number.isNaN(value)) return 0
  return Math.max(0, Math.min(100, value))
}

export default function TrainingStudioLauncher({
  value,
  onChange,
  disabled = false,
}: TrainingStudioLauncherProps) {
  const { t } = useI18n()

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
        <div className="tsl-label">{t('training.launcher.scenario')}</div>
        <div className="tsl-option-grid tsl-option-grid--four">
          {SCENARIO_OPTIONS.map((item) => (
            <button
              key={item.value}
              className={`tsl-option ${value.scenario === item.value ? 'selected' : ''}`}
              type="button"
              onClick={() => updateScenario(item.value)}
              disabled={disabled}
            >
              <span>{t(item.labelKey)}</span>
              {item.descKey && <small>{t(item.descKey)}</small>}
            </button>
          ))}
        </div>
      </div>

      {value.scenario === 'interview' && (
        <>
          <div className="tsl-section">
            <div className="tsl-label">{t('training.launcher.interviewRoles')}</div>
            <div className="tsl-option-grid tsl-option-grid--four">
              {INTERVIEW_ROLE_PRESETS.map((item) => (
                <button
                  key={item.value}
                  className={`tsl-option ${value.interviewRolePreset === item.value ? 'selected' : ''}`}
                  type="button"
                  onClick={() => applyInterviewRolePreset(item)}
                  disabled={disabled}
                >
                  <span>{t(item.labelKey)}</span>
                  {item.descKey && <small>{t(item.descKey)}</small>}
                </button>
              ))}
            </div>
          </div>

          <div className="tsl-section">
            <div className="tsl-label">{t('training.launcher.interviewScenarios')}</div>
            <div className="tsl-preset-grid">
              {INTERVIEW_SCENARIO_PRESETS.map((item) => (
                <button
                  key={item.value}
                  className={`tsl-option tsl-option--compact ${
                    value.interviewScenarioPreset === item.value ? 'selected' : ''
                  }`}
                  type="button"
                  onClick={() => applyInterviewScenarioPreset(item)}
                  disabled={disabled}
                >
                  <span>{t(item.labelKey)}</span>
                  {item.descKey && <small>{t(item.descKey)}</small>}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {value.scenario === 'product_management' && (
        <>
          <div className="tsl-section">
            <div className="tsl-label">{t('training.launcher.productRoles')}</div>
            <div className="tsl-option-grid tsl-option-grid--four">
              {PRODUCT_ROLE_PRESETS.map((item) => (
                <button
                  key={item.value}
                  className={`tsl-option ${value.productRolePreset === item.value ? 'selected' : ''}`}
                  type="button"
                  onClick={() => applyProductRolePreset(item)}
                  disabled={disabled}
                >
                  <span>{t(item.labelKey)}</span>
                  {item.descKey && <small>{t(item.descKey)}</small>}
                </button>
              ))}
            </div>
          </div>

          <div className="tsl-section">
            <div className="tsl-label">{t('training.launcher.productScenarios')}</div>
            <div className="tsl-preset-grid">
              {PRODUCT_SCENARIO_PRESETS.map((item) => (
                <button
                  key={item.value}
                  className={`tsl-option tsl-option--compact ${
                    value.productScenarioPreset === item.value ? 'selected' : ''
                  }`}
                  type="button"
                  onClick={() => applyProductScenarioPreset(item)}
                  disabled={disabled}
                >
                  <span>{t(item.labelKey)}</span>
                  {item.descKey && <small>{t(item.descKey)}</small>}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="tsl-two-col">
        <div className="tsl-section">
          <div className="tsl-label">{t('training.launcher.difficulty')}</div>
          <div className="tsl-option-grid">
            {DIFFICULTY_OPTIONS.map((item) => (
              <button
                key={item.value}
                className={`tsl-option ${value.difficulty === item.value ? 'selected' : ''}`}
                type="button"
                onClick={() => update('difficulty', item.value)}
                disabled={disabled}
              >
                <span>{t(item.labelKey)}</span>
                {item.descKey && <small>{t(item.descKey)}</small>}
              </button>
            ))}
          </div>
        </div>

        <div className="tsl-section">
          <div className="tsl-label">{t('training.launcher.framework')}</div>
          <div className="tsl-option-grid tsl-option-grid--four">
            {FRAMEWORK_OPTIONS.map((item) => (
              <button
                key={item.value}
                className={`tsl-option ${value.framework === item.value ? 'selected' : ''}`}
                type="button"
                onClick={() => update('framework', item.value)}
                disabled={disabled}
              >
                <span>{t(item.labelKey)}</span>
                {item.descKey && <small>{t(item.descKey)}</small>}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="tsl-form-grid">
        <label className="tsl-field">
          <span>{t('training.launcher.role')}</span>
          <input
            value={value.role}
            onChange={(event) => update('role', event.target.value)}
            placeholder={t('training.placeholder.role')}
            disabled={disabled}
          />
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

        <label className="tsl-field tsl-field--wide">
          <span>{t('training.launcher.techStack')}</span>
          <input
            value={value.techStack}
            onChange={(event) => update('techStack', event.target.value)}
            placeholder={t('training.placeholder.techStack')}
            disabled={disabled}
          />
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
    </section>
  )
}
