import {
  DEFAULT_TRAINING_STUDIO_CONFIG,
  DIFFICULTY_OPTIONS,
  FRAMEWORK_OPTIONS,
  SCENARIO_OPTIONS,
  type QuestionMix,
  type TrainingStudioConfig,
} from '../services/trainingStudio'
import './TrainingStudioLauncher.css'

interface TrainingStudioLauncherProps {
  value: TrainingStudioConfig
  onChange: (next: TrainingStudioConfig) => void
  disabled?: boolean
}

const LEVEL_OPTIONS = ['Intern', 'Junior', 'Mid-level', 'Senior', 'Staff', 'Manager']
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
  const update = <K extends keyof TrainingStudioConfig>(key: K, nextValue: TrainingStudioConfig[K]) => {
    onChange({ ...value, [key]: nextValue })
  }

  const updateMix = (key: keyof QuestionMix, nextValue: number) => {
    update('questionMix', {
      ...value.questionMix,
      [key]: clampPercent(nextValue),
    })
  }

  const totalMix = value.questionMix.behavioral + value.questionMix.technical + value.questionMix.pressure

  return (
    <section className="tsl-panel" aria-label="Training Studio configuration">
      <div className="tsl-header">
        <div>
          <h2 className="tsl-title">Communication Training Studio</h2>
          <p className="tsl-subtitle">
            Choose the scenario, pressure, structure, and question mix before generating a practice opponent.
          </p>
        </div>
        <button
          className="tsl-reset"
          type="button"
          onClick={() => onChange(DEFAULT_TRAINING_STUDIO_CONFIG)}
          disabled={disabled}
        >
          Reset
        </button>
      </div>

      <div className="tsl-section">
        <div className="tsl-label">Scenario</div>
        <div className="tsl-option-grid tsl-option-grid--four">
          {SCENARIO_OPTIONS.map((item) => (
            <button
              key={item.value}
              className={`tsl-option ${value.scenario === item.value ? 'selected' : ''}`}
              type="button"
              onClick={() => update('scenario', item.value)}
              disabled={disabled}
            >
              <span>{item.label}</span>
              <small>{item.desc}</small>
            </button>
          ))}
        </div>
      </div>

      <div className="tsl-two-col">
        <div className="tsl-section">
          <div className="tsl-label">Difficulty</div>
          <div className="tsl-option-grid">
            {DIFFICULTY_OPTIONS.map((item) => (
              <button
                key={item.value}
                className={`tsl-option ${value.difficulty === item.value ? 'selected' : ''}`}
                type="button"
                onClick={() => update('difficulty', item.value)}
                disabled={disabled}
              >
                <span>{item.label}</span>
                <small>{item.desc}</small>
              </button>
            ))}
          </div>
        </div>

        <div className="tsl-section">
          <div className="tsl-label">Expression Framework</div>
          <div className="tsl-option-grid tsl-option-grid--four">
            {FRAMEWORK_OPTIONS.map((item) => (
              <button
                key={item.value}
                className={`tsl-option ${value.framework === item.value ? 'selected' : ''}`}
                type="button"
                onClick={() => update('framework', item.value)}
                disabled={disabled}
              >
                <span>{item.label}</span>
                <small>{item.desc}</small>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="tsl-form-grid">
        <label className="tsl-field">
          <span>Role</span>
          <input
            value={value.role}
            onChange={(event) => update('role', event.target.value)}
            placeholder="Example: Frontend Engineer"
            disabled={disabled}
          />
        </label>

        <label className="tsl-field">
          <span>Level</span>
          <select value={value.level} onChange={(event) => update('level', event.target.value)} disabled={disabled}>
            {LEVEL_OPTIONS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>

        <label className="tsl-field tsl-field--wide">
          <span>Tech Stack</span>
          <input
            value={value.techStack}
            onChange={(event) => update('techStack', event.target.value)}
            placeholder="Example: React, TypeScript, Node.js"
            disabled={disabled}
          />
        </label>

        <label className="tsl-field">
          <span>Questions</span>
          <select
            value={value.questionCount}
            onChange={(event) => update('questionCount', Number(event.target.value))}
            disabled={disabled}
          >
            {QUESTION_COUNT_OPTIONS.map((count) => (
              <option key={count} value={count}>
                {count} questions
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="tsl-section">
        <div className="tsl-mix-heading">
          <div className="tsl-label">Question Mix</div>
          <span className={totalMix === 100 ? 'tsl-total ok' : 'tsl-total'}>Total {totalMix}%</span>
        </div>
        <div className="tsl-mix-grid">
          <label className="tsl-range">
            <span>Behavioral</span>
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
            <span>Technical</span>
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
            <span>Pressure</span>
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
