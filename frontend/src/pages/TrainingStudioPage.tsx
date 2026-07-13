import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Keyboard, Loader2, Mic2, Video, Wand2 } from 'lucide-react'
import TrainingStudioLauncher from '../components/TrainingStudioLauncher'
import { startBattle } from '../services/api'
import {
  DEFAULT_TRAINING_STUDIO_CONFIG,
  buildTrainingStudioPrompt,
  toBattleDifficulty,
  type TrainingStudioConfig,
} from '../services/trainingStudio'
import './TrainingStudioPage.css'

type TrainingMode = 'text' | 'voice' | 'video'

const modeOptions: Array<{
  value: TrainingMode
  label: string
  description: string
  icon: typeof Keyboard
}> = [
  {
    value: 'text',
    label: 'Text',
    description: 'Structured written practice with rubrics and replay.',
    icon: Keyboard,
  },
  {
    value: 'voice',
    label: 'Voice',
    description: 'Start in chat with voice controls ready for spoken answers.',
    icon: Mic2,
  },
  {
    value: 'video',
    label: 'Video',
    description: 'Record camera answers and keep the replay attached to messages.',
    icon: Video,
  },
]

function modeInstruction(mode: TrainingMode): string {
  if (mode === 'voice') {
    return 'Session mode: voice. Ask concise questions, wait for spoken answers, and give short turn-by-turn feedback.'
  }
  if (mode === 'video') {
    return 'Session mode: video. Ask answer prompts that work well as recorded video responses and review delivery, structure, and evidence.'
  }
  return 'Session mode: text. Run a focused written communication drill with structured feedback.'
}

export default function TrainingStudioPage() {
  const navigate = useNavigate()
  const [config, setConfig] = useState<TrainingStudioConfig>(DEFAULT_TRAINING_STUDIO_CONFIG)
  const [mode, setMode] = useState<TrainingMode>('voice')
  const [goal, setGoal] = useState('')
  const [starting, setStarting] = useState<'quick' | 'battle' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const prompt = useMemo(() => {
    const base = goal.trim() || `${config.role} ${config.scenario} practice`
    return buildTrainingStudioPrompt(config, `${base}\n\n${modeInstruction(mode)}`)
  }, [config, goal, mode])

  const startQuickSession = async () => {
    setStarting('quick')
    setError(null)
    try {
      const room = await startBattle({
        persona_name: `${config.role || 'Communication'} Coach`,
        persona_role: `${config.level || 'Practice'} ${config.scenario} trainer`,
        persona_style: `${config.difficulty} pressure, ${config.framework.toUpperCase()} feedback, ${mode} response mode`,
        scenario_context: prompt,
        selected_training_points: [
          `${config.framework.toUpperCase()} structure`,
          `${mode} delivery`,
          'evidence-backed answers',
        ],
        difficulty: toBattleDifficulty(config.difficulty),
      })
      navigate(`/chat/${room.id}`)
    } catch (e: any) {
      setError(e?.message || 'Failed to start session')
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
            <h1>Communication Training Studio</h1>
            <p>Pick the scenario, response mode, and pressure profile before entering a live practice room.</p>
          </div>
          <button
            className="training-studio-primary"
            type="button"
            onClick={startQuickSession}
            disabled={starting !== null}
          >
            {starting === 'quick' ? <Loader2 size={16} className="training-studio-spin" /> : <Wand2 size={16} />}
            Start Room
          </button>
        </header>

        <section className="training-studio-mode-panel" aria-label="Response mode">
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
                <span>{item.label}</span>
                <small>{item.description}</small>
              </button>
            )
          })}
        </section>

        <div className="training-studio-grid">
          <div className="training-studio-main">
            <label className="training-studio-goal">
              <span>Practice Goal</span>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={4}
                placeholder="Example: Practice answering senior frontend system-design interview questions with stronger evidence and tighter structure."
                disabled={starting !== null}
              />
            </label>

            <TrainingStudioLauncher value={config} onChange={setConfig} disabled={starting !== null} />
          </div>

          <aside className="training-studio-side" aria-label="Session actions">
            <div className="training-studio-action-block">
              <h2>Launch Path</h2>
              <button
                className="training-studio-action"
                type="button"
                onClick={startQuickSession}
                disabled={starting !== null}
              >
                {starting === 'quick' ? <Loader2 size={16} className="training-studio-spin" /> : <Keyboard size={16} />}
                Open Chat Room
              </button>
              <button
                className="training-studio-action secondary"
                type="button"
                onClick={startGuidedBattle}
                disabled={starting !== null}
              >
                <Wand2 size={16} />
                Open Battle Prep Flow
              </button>
              {error && <div className="training-studio-error">{error}</div>}
            </div>

            <div className="training-studio-action-block">
              <h2>Mode Entry</h2>
              <div className="training-studio-mode-note">
                {mode === 'voice' && 'After entering the room, use the microphone button in the chat input to answer by voice.'}
                {mode === 'video' && 'After entering the room, use the video button in the chat input to record and send answers.'}
                {mode === 'text' && 'After entering the room, type answers in the chat input and request analysis or coaching.'}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
