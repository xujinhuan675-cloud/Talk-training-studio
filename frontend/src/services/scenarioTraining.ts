import type { ScenarioTrainingCard, ScenarioTrainingProgress } from '../data/trainingScenarios'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface ScenarioTrainingTemplateDTO {
  id: string
  title: string
  description: string
  customer_profile: string
  difficulty: ScenarioTrainingCard['difficulty']
  category: ScenarioTrainingCard['category']
  required: boolean
  status: ScenarioTrainingCard['status']
  score?: number | null
  last_practiced_at?: string | null
  opening_line: string
  persona: {
    name: string
    role: string
    style: string
  }
  learner_role: string
  framework: ScenarioTrainingCard['framework']
  training_points: string[]
}

interface ScenarioTrainingProgressDTO {
  scenario_id: string
  user_id?: string | null
  team_id?: string | null
  status: ScenarioTrainingCard['status']
  score?: number | null
  score_status?: 'ready' | 'pending'
  overall_score?: number | null
  evaluation_id?: number | null
  last_practiced_at?: string | null
  training_session_id: string
  report_id?: string | null
  score_id?: string | null
}

const SCENARIO_TEMPLATE_API = '/api/v1/training-studio/scenario-templates'
const SCENARIO_PROGRESS_API = '/api/v1/training-studio/scenario-progress'

export interface ScenarioTrainingProgressScope {
  userId?: string | null
  teamId?: string | null
}

function toScenarioTrainingCard(dto: ScenarioTrainingTemplateDTO): ScenarioTrainingCard {
  return {
    id: dto.id,
    title: dto.title,
    description: dto.description,
    customerProfile: dto.customer_profile,
    difficulty: dto.difficulty,
    category: dto.category,
    required: dto.required,
    status: dto.status,
    score: dto.score ?? undefined,
    lastPracticedAt: dto.last_practiced_at ?? undefined,
    openingLine: dto.opening_line,
    persona: {
      name: dto.persona.name,
      role: dto.persona.role,
      style: dto.persona.style,
    },
    learnerRole: dto.learner_role,
    framework: dto.framework,
    trainingPoints: [...dto.training_points],
  }
}

function toScenarioTrainingProgress(items: ScenarioTrainingProgressDTO[]): ScenarioTrainingProgress {
  return items.reduce<ScenarioTrainingProgress>((progress, item) => {
    progress[item.scenario_id] = {
      status: item.status,
      score: item.score ?? undefined,
      scoreStatus: item.score_status ?? undefined,
      overallScore: item.overall_score ?? undefined,
      evaluationId: item.evaluation_id ?? undefined,
      lastPracticedAt: item.last_practiced_at ?? undefined,
      userId: item.user_id ?? undefined,
      teamId: item.team_id ?? undefined,
      trainingSessionId: item.training_session_id,
      reportId: item.report_id ?? undefined,
      scoreId: item.score_id ?? undefined,
    }
    return progress
  }, {})
}

function progressUrl(scope: ScenarioTrainingProgressScope = {}): string {
  const params = new URLSearchParams()
  if (scope.userId) params.set('user_id', scope.userId)
  if (scope.teamId) params.set('team_id', scope.teamId)
  const query = params.toString()
  return `${SCENARIO_PROGRESS_API}${query ? `?${query}` : ''}`
}

async function readError(resp: Response, fallback: string): Promise<Error> {
  const json = await resp.json().catch(() => null)
  const detail = typeof json?.detail === 'string' ? json.detail : json?.detail?.message
  return new Error(json?.error?.details || detail || json?.message || `${fallback}: ${resp.status}`)
}

export async function fetchScenarioTrainingCatalog(): Promise<ScenarioTrainingCard[]> {
  const resp = await fetch(SCENARIO_TEMPLATE_API)
  if (!resp.ok) {
    throw await readError(resp, 'Failed to fetch scenario templates')
  }
  const json: ApiResponse<ScenarioTrainingTemplateDTO[]> = await resp.json()
  return json.data.map(toScenarioTrainingCard)
}

export async function fetchScenarioTrainingProgress(
  scope: ScenarioTrainingProgressScope = {},
): Promise<ScenarioTrainingProgress> {
  const resp = await fetch(progressUrl(scope))
  if (!resp.ok) {
    throw await readError(resp, 'Failed to fetch scenario progress')
  }
  const json: ApiResponse<ScenarioTrainingProgressDTO[]> = await resp.json()
  return toScenarioTrainingProgress(json.data)
}
