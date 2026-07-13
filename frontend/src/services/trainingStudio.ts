import type { Translate, TranslationKey, TranslationParams } from '../i18n'

export type TrainingScenario = 'interview' | 'sales' | 'negotiation' | 'workplace'
export type TrainingDifficulty = 'easy' | 'medium' | 'hard'
export type ExpressionFramework = 'prep' | 'star' | 'scqa' | 'pyramid'
export type TrainingLevel = 'intern' | 'junior' | 'mid' | 'senior' | 'staff' | 'manager'

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
  level: TrainingLevel
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

interface LocalizedOption<T extends string> {
  value: T
  labelKey: TranslationKey
  descKey?: TranslationKey
  fallbackLabel: string
  fallbackDesc?: string
}

export const SCENARIO_OPTIONS: LocalizedOption<TrainingScenario>[] = [
  {
    value: 'interview',
    labelKey: 'training.scenario.interview.label',
    descKey: 'training.scenario.interview.desc',
    fallbackLabel: 'Interview',
    fallbackDesc: 'Interview answers and follow-ups',
  },
  {
    value: 'sales',
    labelKey: 'training.scenario.sales.label',
    descKey: 'training.scenario.sales.desc',
    fallbackLabel: 'Sales',
    fallbackDesc: 'Objections, value, and next steps',
  },
  {
    value: 'negotiation',
    labelKey: 'training.scenario.negotiation.label',
    descKey: 'training.scenario.negotiation.desc',
    fallbackLabel: 'Negotiation',
    fallbackDesc: 'Trade-offs, leverage, and concessions',
  },
  {
    value: 'workplace',
    labelKey: 'training.scenario.workplace.label',
    descKey: 'training.scenario.workplace.desc',
    fallbackLabel: 'Workplace',
    fallbackDesc: 'Alignment, feedback, and reporting',
  },
]

export const DIFFICULTY_OPTIONS: LocalizedOption<TrainingDifficulty>[] = [
  {
    value: 'easy',
    labelKey: 'training.difficulty.easy.label',
    descKey: 'training.difficulty.easy.desc',
    fallbackLabel: 'Easy',
    fallbackDesc: 'Gentle prompts',
  },
  {
    value: 'medium',
    labelKey: 'training.difficulty.medium.label',
    descKey: 'training.difficulty.medium.desc',
    fallbackLabel: 'Medium',
    fallbackDesc: 'Normal pressure',
  },
  {
    value: 'hard',
    labelKey: 'training.difficulty.hard.label',
    descKey: 'training.difficulty.hard.desc',
    fallbackLabel: 'Hard',
    fallbackDesc: 'Tough follow-ups',
  },
]

export const FRAMEWORK_OPTIONS: LocalizedOption<ExpressionFramework>[] = [
  {
    value: 'prep',
    labelKey: 'training.framework.prep.label',
    descKey: 'training.framework.prep.desc',
    fallbackLabel: 'PREP',
    fallbackDesc: 'Point, reason, example, point',
  },
  {
    value: 'star',
    labelKey: 'training.framework.star.label',
    descKey: 'training.framework.star.desc',
    fallbackLabel: 'STAR',
    fallbackDesc: 'Situation, task, action, result',
  },
  {
    value: 'scqa',
    labelKey: 'training.framework.scqa.label',
    descKey: 'training.framework.scqa.desc',
    fallbackLabel: 'SCQA',
    fallbackDesc: 'Situation, complication, question, answer',
  },
  {
    value: 'pyramid',
    labelKey: 'training.framework.pyramid.label',
    descKey: 'training.framework.pyramid.desc',
    fallbackLabel: 'Pyramid',
    fallbackDesc: 'Answer first, then layered support',
  },
]

export const TRAINING_LEVEL_OPTIONS: LocalizedOption<TrainingLevel>[] = [
  { value: 'intern', labelKey: 'training.level.intern.label', fallbackLabel: 'Intern' },
  { value: 'junior', labelKey: 'training.level.junior.label', fallbackLabel: 'Junior' },
  { value: 'mid', labelKey: 'training.level.mid.label', fallbackLabel: 'Mid-level' },
  { value: 'senior', labelKey: 'training.level.senior.label', fallbackLabel: 'Senior' },
  { value: 'staff', labelKey: 'training.level.staff.label', fallbackLabel: 'Staff' },
  { value: 'manager', labelKey: 'training.level.manager.label', fallbackLabel: 'Manager' },
]

export const DEFAULT_TRAINING_STUDIO_CONFIG: TrainingStudioConfig = {
  scenario: 'interview',
  difficulty: 'medium',
  framework: 'star',
  role: 'Frontend Engineer',
  level: 'mid',
  techStack: 'React, TypeScript',
  questionMix: {
    behavioral: 35,
    technical: 45,
    pressure: 20,
  },
  questionCount: 8,
}

function formatFallback(template: string, params?: TranslationParams): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(params[key] ?? `{${key}}`))
}

function translate(t: Translate | undefined, key: TranslationKey, fallback: string, params?: TranslationParams): string {
  return t ? t(key, params) : formatFallback(fallback, params)
}

function optionLabel<T extends string>(options: LocalizedOption<T>[], value: T, t?: Translate): string {
  const option = options.find((item) => item.value === value)
  return option ? translate(t, option.labelKey, option.fallbackLabel) : value
}

export function getTrainingScenarioLabel(scenario: TrainingScenario, t?: Translate): string {
  return optionLabel(SCENARIO_OPTIONS, scenario, t)
}

export function getTrainingDifficultyLabel(difficulty: TrainingDifficulty, t?: Translate): string {
  return optionLabel(DIFFICULTY_OPTIONS, difficulty, t)
}

export function getExpressionFrameworkLabel(framework: ExpressionFramework, t?: Translate): string {
  return optionLabel(FRAMEWORK_OPTIONS, framework, t)
}

export function getTrainingLevelLabel(level: TrainingLevel, t?: Translate): string {
  return optionLabel(TRAINING_LEVEL_OPTIONS, level, t)
}

export function getDefaultTrainingStudioConfig(t?: Translate): TrainingStudioConfig {
  return {
    ...DEFAULT_TRAINING_STUDIO_CONFIG,
    role: translate(t, 'training.defaults.role', DEFAULT_TRAINING_STUDIO_CONFIG.role),
    techStack: translate(t, 'training.defaults.techStack', DEFAULT_TRAINING_STUDIO_CONFIG.techStack),
    questionMix: { ...DEFAULT_TRAINING_STUDIO_CONFIG.questionMix },
  }
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

export function buildTrainingStudioPrompt(config: TrainingStudioConfig, description: string, t?: Translate): string {
  const mix = normalizeQuestionMix(config.questionMix)
  const scenario = getTrainingScenarioLabel(config.scenario, t)
  const difficulty = getTrainingDifficultyLabel(config.difficulty, t)
  const framework = getExpressionFrameworkLabel(config.framework, t)
  const level = getTrainingLevelLabel(config.level, t)
  const notSpecified = translate(t, 'training.prompt.notSpecified', 'Not specified')

  return [
    description.trim(),
    '',
    translate(t, 'training.prompt.heading', 'Training Studio configuration:'),
    `- ${translate(t, 'training.prompt.scenario', 'Scenario')}: ${scenario}`,
    `- ${translate(t, 'training.prompt.difficulty', 'Difficulty')}: ${difficulty}`,
    `- ${translate(t, 'training.prompt.framework', 'Expression framework')}: ${framework}`,
    `- ${translate(t, 'training.prompt.role', 'Target role')}: ${config.role || notSpecified}`,
    `- ${translate(t, 'training.prompt.level', 'Level')}: ${level || notSpecified}`,
    `- ${translate(t, 'training.prompt.techStack', 'Tech stack')}: ${config.techStack || notSpecified}`,
    `- ${translate(t, 'training.prompt.questionMix', 'Question mix')}: ${translate(t, 'training.launcher.behavioral', 'behavioral')} ${mix.behavioral}%, ${translate(t, 'training.launcher.technical', 'technical')} ${mix.technical}%, ${translate(t, 'training.launcher.pressure', 'pressure')} ${mix.pressure}%`,
    `- ${translate(t, 'training.prompt.questionCount', 'Question count')}: ${config.questionCount}`,
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
