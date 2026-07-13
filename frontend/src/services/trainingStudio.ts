export type TrainingScenario = 'interview' | 'sales' | 'negotiation' | 'workplace'
export type TrainingDifficulty = 'easy' | 'medium' | 'hard'
export type ExpressionFramework = 'prep' | 'star' | 'scqa' | 'pyramid'

export interface QuestionMix {
  behavioral: number
  technical: number
  pressure: number
}

export interface TrainingStudioConfig {
  scenario: TrainingScenario
  difficulty: TrainingDifficulty
  framework: ExpressionFramework
  role: string
  level: string
  techStack: string
  questionMix: QuestionMix
  questionCount: number
}

export interface VideoAnswerUploadResult {
  filename: string
  url: string
  mimeType: string
  size: number
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const TRAINING_STUDIO_API_BASE = '/api/v1/training-studio'

export const SCENARIO_OPTIONS: { value: TrainingScenario; label: string; desc: string }[] = [
  { value: 'interview', label: 'Interview', desc: 'Interview answers and follow-ups' },
  { value: 'sales', label: 'Sales', desc: 'Objections, value, and next steps' },
  { value: 'negotiation', label: 'Negotiation', desc: 'Trade-offs, leverage, and concessions' },
  { value: 'workplace', label: 'Workplace', desc: 'Alignment, feedback, and reporting' },
]

export const DIFFICULTY_OPTIONS: { value: TrainingDifficulty; label: string; desc: string }[] = [
  { value: 'easy', label: 'Easy', desc: 'Gentle prompts' },
  { value: 'medium', label: 'Medium', desc: 'Normal pressure' },
  { value: 'hard', label: 'Hard', desc: 'Tough follow-ups' },
]

export const FRAMEWORK_OPTIONS: { value: ExpressionFramework; label: string; desc: string }[] = [
  { value: 'prep', label: 'PREP', desc: 'Point, reason, example, point' },
  { value: 'star', label: 'STAR', desc: 'Situation, task, action, result' },
  { value: 'scqa', label: 'SCQA', desc: 'Situation, complication, question, answer' },
  { value: 'pyramid', label: 'Pyramid', desc: 'Answer first, then layered support' },
]

export const DEFAULT_TRAINING_STUDIO_CONFIG: TrainingStudioConfig = {
  scenario: 'interview',
  difficulty: 'medium',
  framework: 'star',
  role: 'Frontend Engineer',
  level: 'Mid-level',
  techStack: 'React, TypeScript',
  questionMix: {
    behavioral: 35,
    technical: 45,
    pressure: 20,
  },
  questionCount: 8,
}

export function normalizeQuestionMix(mix: QuestionMix): QuestionMix {
  const total = mix.behavioral + mix.technical + mix.pressure
  if (total <= 0) return DEFAULT_TRAINING_STUDIO_CONFIG.questionMix

  const behavioral = Math.round((mix.behavioral / total) * 100)
  const technical = Math.round((mix.technical / total) * 100)
  return {
    behavioral,
    technical,
    pressure: Math.max(0, 100 - behavioral - technical),
  }
}

export function toBattleDifficulty(difficulty: TrainingDifficulty): 'easy' | 'normal' | 'hard' {
  return difficulty === 'medium' ? 'normal' : difficulty
}

export function buildTrainingStudioPrompt(config: TrainingStudioConfig, description: string): string {
  const mix = normalizeQuestionMix(config.questionMix)
  const scenario = SCENARIO_OPTIONS.find((item) => item.value === config.scenario)?.label ?? config.scenario
  const framework = FRAMEWORK_OPTIONS.find((item) => item.value === config.framework)?.label ?? config.framework

  return [
    description.trim(),
    '',
    'Training Studio configuration:',
    `- Scenario: ${scenario}`,
    `- Difficulty: ${config.difficulty}`,
    `- Expression framework: ${framework}`,
    `- Target role: ${config.role || 'Not specified'}`,
    `- Level: ${config.level || 'Not specified'}`,
    `- Tech stack: ${config.techStack || 'Not specified'}`,
    `- Question mix: behavioral ${mix.behavioral}%, technical ${mix.technical}%, pressure ${mix.pressure}%`,
    `- Question count: ${config.questionCount}`,
  ].join('\n')
}

function extensionForVideoMimeType(mimeType: string): string {
  const clean = mimeType.split(';')[0].trim().toLowerCase()
  if (clean === 'video/mp4') return '.mp4'
  if (clean === 'video/quicktime') return '.mov'
  if (clean === 'video/ogg') return '.ogv'
  if (clean === 'video/x-matroska') return '.mkv'
  return '.webm'
}

export async function uploadVideoAnswer(
  blob: Blob,
  filename = `video-answer-${Date.now()}${extensionForVideoMimeType(blob.type)}`,
): Promise<VideoAnswerUploadResult> {
  const resp = await fetch(`${TRAINING_STUDIO_API_BASE}/video-answers`, {
    method: 'POST',
    headers: {
      'Content-Type': blob.type || 'video/webm',
      'X-Filename': filename,
    },
    body: blob,
  })
  if (!resp.ok) {
    throw new Error(`Failed to upload video answer: ${resp.status}`)
  }
  const json: ApiResponse<VideoAnswerUploadResult> = await resp.json()
  return json.data
}
