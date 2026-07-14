import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Keyboard, Loader2, Mic2, Video, Wand2 } from 'lucide-react'
import TrainingStudioLauncher from '../components/TrainingStudioLauncher'
import { startBattle } from '../services/api'
import { createTrainingSession, startTrainingSession } from '../services/trainingSession'
import { buildTrainingModeChatPath, type TrainingMode } from '../services/trainingMode'
import {
  buildTrainingStudioPrompt,
  getDefaultTrainingStudioConfig,
  getExpressionFrameworkLabel,
  getInterviewScenarioPreset,
  getProductScenarioPreset,
  getTrainingDifficultyLabel,
  getTrainingLevelLabel,
  getTrainingScenarioLabel,
  toBattleDifficulty,
  type TrainingStudioConfig,
} from '../services/trainingStudio'
import { useI18n, type Translate, type TranslationKey } from '../i18n'
import './TrainingStudioPage.css'

const modeOptions: Array<{
  value: TrainingMode
  labelKey: TranslationKey
  descriptionKey: TranslationKey
  icon: typeof Keyboard
}> = [
  {
    value: 'text',
    labelKey: 'training.mode.text.label',
    descriptionKey: 'training.mode.text.desc',
    icon: Keyboard,
  },
  {
    value: 'voice',
    labelKey: 'training.mode.voice.label',
    descriptionKey: 'training.mode.voice.desc',
    icon: Mic2,
  },
  {
    value: 'video',
    labelKey: 'training.mode.video.label',
    descriptionKey: 'training.mode.video.desc',
    icon: Video,
  },
]

const modeLabelKeys: Record<TrainingMode, TranslationKey> = {
  text: 'training.mode.text.label',
  voice: 'training.mode.voice.label',
  video: 'training.mode.video.label',
}

function getModeLabel(mode: TrainingMode, t: Translate): string {
  return t(modeLabelKeys[mode])
}

function modeInstruction(mode: TrainingMode, t: Translate): string {
  if (mode === 'voice') {
    return t('training.mode.voice.instruction')
  }
  if (mode === 'video') {
    return t('training.mode.video.instruction')
  }
  return t('training.mode.text.instruction')
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function splitTechStack(value: string, fallback: string): string[] {
  const items = value
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
  return items.length > 0 ? items : [fallback]
}

export default function TrainingStudioPage() {
  const navigate = useNavigate()
  const { t } = useI18n()
  const [config, setConfig] = useState<TrainingStudioConfig>(() => getDefaultTrainingStudioConfig(t))
  const previousDefaultsRef = useRef(getDefaultTrainingStudioConfig(t))
  const [mode, setMode] = useState<TrainingMode>('voice')
  const [goal, setGoal] = useState('')
  const [starting, setStarting] = useState<'quick' | 'battle' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const previousDefaults = previousDefaultsRef.current
    const nextDefaults = getDefaultTrainingStudioConfig(t)

    setConfig((current) => ({
      ...current,
      role: current.role === previousDefaults.role ? nextDefaults.role : current.role,
      techStack: current.techStack === previousDefaults.techStack ? nextDefaults.techStack : current.techStack,
    }))
    previousDefaultsRef.current = nextDefaults
  }, [t])

  const prompt = useMemo(() => {
    const scenario = getTrainingScenarioLabel(config.scenario, t)
    const role = config.role.trim() || t('training.defaults.roleFallback')
    const base = goal.trim() || t('training.prompt.defaultGoal', { role, scenario })
    return buildTrainingStudioPrompt(config, `${base}\n\n${modeInstruction(mode, t)}`, t)
  }, [config, goal, mode, t])

  const startQuickSession = async () => {
    setStarting('quick')
    setError(null)
    try {
      const role = config.role.trim() || t('training.defaults.roleFallback')
      const scenario = getTrainingScenarioLabel(config.scenario, t)
      const difficulty = getTrainingDifficultyLabel(config.difficulty, t)
      const framework = getExpressionFrameworkLabel(config.framework, t)
      const level = getTrainingLevelLabel(config.level, t)
      const modeLabel = getModeLabel(mode, t)
      const interviewScenarioPreset = getInterviewScenarioPreset(config.interviewScenarioPreset)
      const productScenarioPreset = getProductScenarioPreset(config.productScenarioPreset)
      const interviewStakeholder = config.scenario === 'interview' ? interviewScenarioPreset : undefined
      const productStakeholder = config.scenario === 'product_management' ? productScenarioPreset : undefined
      const scenarioStakeholder = interviewStakeholder ?? productStakeholder
      const trainingSession = await createTrainingSession({
        mode,
        task_config: {
          role,
          level,
          tech_stack: splitTechStack(config.techStack, scenario),
          question_type_ratios: { ...config.questionMix },
          question_count: config.questionCount,
          framework: config.framework,
          difficulty: config.difficulty,
          category: config.scenario,
        },
      })

      const room = await startBattle({
        persona_name: scenarioStakeholder
          ? t(scenarioStakeholder.personaNameKey)
          : t('training.prompt.personaName', { role }),
        persona_role: scenarioStakeholder
          ? t(scenarioStakeholder.personaRoleKey)
          : t('training.prompt.personaRole', { level, scenario }),
        persona_style: scenarioStakeholder
          ? t(scenarioStakeholder.personaStyleKey, { difficulty, framework, mode: modeLabel })
          : t('training.prompt.personaStyle', { difficulty, framework, mode: modeLabel }),
        scenario_context: prompt,
        selected_training_points: [
          t('training.prompt.structurePoint', { framework }),
          ...(interviewStakeholder
            ? [
                t('training.prompt.interviewEvidencePoint'),
                t('training.prompt.interviewFollowupPoint'),
              ]
            : []),
          ...(productStakeholder
            ? [
                t('training.prompt.productAlignmentPoint'),
                t('training.prompt.productTradeoffPoint'),
              ]
            : []),
          t('training.prompt.deliveryPoint', { mode: modeLabel }),
          t('training.prompt.evidencePoint'),
        ],
        difficulty: toBattleDifficulty(config.difficulty),
      })
      const startedSession = await startTrainingSession(trainingSession.session_id, {
        room_id: room.id,
      })
      navigate(buildTrainingModeChatPath(room.id, mode, startedSession.session_id), {
        state: {
          source: 'training-studio',
          trainingMode: mode,
          trainingSessionId: startedSession.session_id,
        },
      })
    } catch (e: unknown) {
      setError(getErrorMessage(e, t('training.error.startFailed')))
      setStarting(null)
    }
  }

  const startGuidedBattle = async () => {
    navigate('/battle-prep')
  }

  return (
    <div className="training-studio-page">
      <div className="training-studio-shell">
        <header className="training-studio-header">
          <div>
            <h1>{t('training.page.title')}</h1>
            <p>{t('training.page.subtitle')}</p>
          </div>
          <button
            className="training-studio-primary"
            type="button"
            onClick={startQuickSession}
            disabled={starting !== null}
          >
            {starting === 'quick' ? <Loader2 size={16} className="training-studio-spin" /> : <Wand2 size={16} />}
            {t('training.page.startRoom')}
          </button>
        </header>

        <section className="training-studio-mode-panel" aria-label={t('training.page.responseModeAria')}>
          {modeOptions.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.value}
                className={`training-studio-mode ${mode === item.value ? 'selected' : ''}`}
                type="button"
                onClick={() => setMode(item.value)}
                disabled={starting !== null}
              >
                <Icon size={20} />
                <span>{t(item.labelKey)}</span>
                <small>{t(item.descriptionKey)}</small>
              </button>
            )
          })}
        </section>

        <div className="training-studio-grid">
          <div className="training-studio-main">
            <label className="training-studio-goal">
              <span>{t('training.goal.label')}</span>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={4}
                placeholder={t('training.goal.placeholder')}
                disabled={starting !== null}
              />
            </label>

            <TrainingStudioLauncher value={config} onChange={setConfig} disabled={starting !== null} />
          </div>

          <aside className="training-studio-side" aria-label={t('training.side.aria')}>
            <div className="training-studio-action-block">
              <h2>{t('training.launch.title')}</h2>
              <button
                className="training-studio-action"
                type="button"
                onClick={startQuickSession}
                disabled={starting !== null}
              >
                {starting === 'quick' ? <Loader2 size={16} className="training-studio-spin" /> : <Keyboard size={16} />}
                {t('training.launch.openChat')}
              </button>
              <button
                className="training-studio-action secondary"
                type="button"
                onClick={startGuidedBattle}
                disabled={starting !== null}
              >
                <Wand2 size={16} />
                {t('training.launch.openBattlePrep')}
              </button>
              {error && <div className="training-studio-error">{error}</div>}
            </div>

            <div className="training-studio-action-block">
              <h2>{t('training.modeEntry.title')}</h2>
              <div className="training-studio-mode-note">
                {mode === 'voice' && t('training.modeEntry.voice')}
                {mode === 'video' && t('training.modeEntry.video')}
                {mode === 'text' && t('training.modeEntry.text')}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
