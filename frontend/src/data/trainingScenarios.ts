import type { TrainingMode } from '../services/trainingMode'
import type { TrainingTaskConfigDTO } from '../services/trainingSession'
import { getDefaultDimensionWeights } from './scenarioConfig'

export type ScenarioTrainingDifficulty = 'easy' | 'medium' | 'hard' | 'expert'
export type ScenarioTrainingCategory = 'sales' | 'customer_service' | 'negotiation' | 'interview' | 'workplace'
export type ScenarioTrainingStatus = 'not_started' | 'in_progress' | 'completed' | 'failed'

export interface ScenarioTrainingCard {
  id: string
  title: string
  description: string
  customerProfile: string
  difficulty: ScenarioTrainingDifficulty
  category: ScenarioTrainingCategory
  required: boolean
  status: ScenarioTrainingStatus
  score?: number
  scoreStatus?: 'ready' | 'pending'
  overallScore?: number
  evaluationId?: number
  lastPracticedAt?: string
  openingLine: string
  persona: {
    name: string
    role: string
    style: string
  }
  learnerRole: string
  framework: 'prep' | 'star' | 'scqa' | 'pyramid'
  trainingPoints: string[]
}

export interface ScenarioTrainingProgressItem extends Pick<ScenarioTrainingCard, 'status' | 'score' | 'lastPracticedAt'> {
  userId?: string
  teamId?: string
  scoreStatus?: 'ready' | 'pending'
  overallScore?: number
  evaluationId?: number
  trainingSessionId?: string
  reportId?: string
  scoreId?: string
  failureReason?: string
}

export type ScenarioTrainingProgress = Partial<Record<string, ScenarioTrainingProgressItem>>

export interface ScenarioTrainingRouteState {
  source: 'scenario-training'
  scenarioTrainingId: string
  scenarioTitle: string
  scenarioDescription: string
  scenarioCustomerProfile: string
  scenarioOpeningLine: string
  scenarioPersonaName: string
  scenarioPersonaRole: string
  scenarioPersonaStyle: string
  scenarioLearnerRole: string
  scenarioDifficulty: ScenarioTrainingDifficulty
  scenarioCategory: ScenarioTrainingCategory
  scenarioRequired: boolean
  scenarioTrainingPoints: string[]
}

export interface ScenarioScoreDimension {
  id: string
  name: string
  description: string
  weight: number
  enabled: boolean
}

export interface ScenarioLeaderboardUser {
  userId: string
  name: string
  teamId: string
  teamName: string
  roleName?: string
}

export interface ScenarioLeaderboardRow {
  userId: string
  name: string
  teamId: string
  teamName: string
  roleName?: string
  rank: number
  completedRequired: number
  totalRequired: number
  completionRate: number
  averageScore: number | null
  totalScore: number
  practicedCount: number
  pendingCount: number
  unfinishedRequired: string[]
  weakestDimension: string | null
}

export interface ScenarioLeaderboardProgressUser extends ScenarioLeaderboardUser {
  progress: ScenarioTrainingProgress
  useCatalogFallback?: boolean
}

export interface ScenarioLeaderboardScenarioRef {
  scenarioId: string
  title: string
}

export interface ScenarioLeaderboardRankRow extends ScenarioLeaderboardUser {
  rank: number
  averageScore: number | null
  completedRequired: number
  totalRequired: number
  completionRate: number
  practicedCount: number
  latestPracticedAt?: string
  isCurrentUser: boolean
}

export interface ScenarioLeaderboardUnfinishedRow extends ScenarioLeaderboardUser {
  averageScore: number | null
  completedRequired: number
  totalRequired: number
  completionRate: number
  practicedCount: number
  latestPracticedAt?: string
  unfinishedRequired: ScenarioLeaderboardScenarioRef[]
  status: 'in_progress' | 'not_started'
  isCurrentUser: boolean
}

export interface ScenarioLeaderboardAbilityDimension {
  dimensionId: string
  name: string
  averageScore: number
  isWeak: boolean
  sampleCount: number
  scenarioTitles: string[]
}

export interface ScenarioLeaderboardScenarioAverage extends ScenarioLeaderboardScenarioRef {
  difficulty: ScenarioTrainingDifficulty
  category: ScenarioTrainingCategory
  required: boolean
  averageScore: number
  participantCount: number
}

export interface ScenarioLeaderboardScenarioStat extends ScenarioLeaderboardScenarioRef {
  difficulty: ScenarioTrainingDifficulty
  category: ScenarioTrainingCategory
  required: boolean
  status: ScenarioTrainingStatus
  score: number | null
  teamAverage: number | null
  gap: number | null
  practiced: boolean
  lastPracticedAt?: string
}

export type ScenarioLeaderboardPersonalStatus = 'ranked' | 'partial' | 'unstart'

export interface ScenarioLeaderboardPersonalOverview {
  user: ScenarioLeaderboardUser
  status: ScenarioLeaderboardPersonalStatus
  rank: number | null
  averageScore: number | null
  overallAverage: number | null
  completedRequired: number
  totalRequired: number
  completionRate: number
  practicedCount: number
  latestPracticedAt?: string
  unfinishedRequired: ScenarioLeaderboardScenarioRef[]
  abilityProfile: ScenarioLeaderboardAbilityDimension[]
  scenarioStats: ScenarioLeaderboardScenarioStat[]
}

export interface ScenarioLeaderboardTeamOverview {
  participants: number
  ranked: number
  unfinishedActive: number
  unfinishedAll: number
  teamAverage: number | null
  ranks: ScenarioLeaderboardRankRow[]
  unfinished: ScenarioLeaderboardUnfinishedRow[]
  weakDimensions: ScenarioLeaderboardAbilityDimension[]
  scenarioAverages: ScenarioLeaderboardScenarioAverage[]
}

export interface ScenarioLeaderboardSummary {
  totalRequired: number
  totalUsers: number
  team: ScenarioLeaderboardTeamOverview
  personal: ScenarioLeaderboardPersonalOverview | null
}

const PROGRESS_STORAGE_KEY = 'talkwise.scenarioTraining.progress.v1'

export const defaultScenarioScoreDimensions: ScenarioScoreDimension[] = [
  {
    id: 'trust_discovery',
    name: '信任与探需',
    description: '是否先建立基本信任，并用开放问题确认真实需求、预算、顾虑和决策条件。',
    weight: 25,
    enabled: true,
  },
  {
    id: 'value_clarity',
    name: '价值表达',
    description: '是否用客户语言讲清价值、边界、证据和与场景相关的收益。',
    weight: 25,
    enabled: true,
  },
  {
    id: 'objection_handling',
    name: '异议处理',
    description: '是否正面处理价格、风险、竞品、情绪或实施阻力，而不是绕开问题。',
    weight: 25,
    enabled: true,
  },
  {
    id: 'next_step',
    name: '推进下一步',
    description: '是否明确可执行的下一步、承诺人、时间点和双方需要准备的信息。',
    weight: 25,
    enabled: true,
  },
]

export interface ScenarioTrainingProgressScope {
  userId?: string | null
  teamId?: string | null
}

function progressStorageKey(scope?: ScenarioTrainingProgressScope): string {
  const userId = scope?.userId?.trim()
  const teamId = scope?.teamId?.trim()
  if (!userId && !teamId) return PROGRESS_STORAGE_KEY
  return `${PROGRESS_STORAGE_KEY}:${userId || 'anonymous'}:${teamId || 'no-team'}`
}

const difficultyToTrainingStudio: Record<ScenarioTrainingDifficulty, 'easy' | 'medium' | 'hard'> = {
  easy: 'easy',
  medium: 'medium',
  hard: 'hard',
  expert: 'hard',
}

const categoryToTrainingStudio: Record<ScenarioTrainingCategory, string> = {
  sales: 'sales',
  customer_service: 'workplace',
  negotiation: 'negotiation',
  interview: 'interview',
  workplace: 'workplace',
}

const scenarioDifficultyBehavior: Record<ScenarioTrainingDifficulty, string> = {
  easy: 'Keep 1-2 normal concerns, listen when the learner answers clearly, but do not agree immediately.',
  medium: 'Hold clear concerns from the profile. You need grounded, non-pushy answers before you soften.',
  hard: 'Actively raise objections, compare alternatives, test price/value claims, and push back on vague or scripted answers.',
  expert: 'Stay highly guarded. Use probing, reversals, price pressure, emotional doubt, and only soften gradually after several strong turns.',
}

export const scenarioTrainingCatalog: ScenarioTrainingCard[] = [
  {
    id: 'daily-upward-results-report',
    title: '向上今日成果汇报',
    description: '向主管用 3 分钟汇报今日关键进展、风险和明日计划，争取清晰反馈与资源支持。',
    customerProfile: '时间有限的直属主管，关注结果、风险、优先级和是否需要介入。',
    difficulty: 'medium',
    category: 'workplace',
    required: false,
    status: 'not_started',
    openingLine: '我现在只有几分钟，你直接说今天最重要的成果、风险，以及你明天准备怎么推进。',
    persona: {
      name: '周经理',
      role: '关注结果的直属主管',
      style: '节奏快、追问重点，会要求用事实和数字说明影响，不接受泛泛汇报。',
    },
    learnerRole: 'Team Member',
    framework: 'pyramid',
    trainingPoints: ['先给结论和成果', '用事实说明影响', '暴露风险并提出下一步请求'],
  },
  {
    id: 'new-customer-discount',
    title: '新客优惠咨询',
    description: '门店新客想了解价格、服务边界和是否值得当场下单。',
    customerProfile: '首次到店客户，预算敏感，愿意尝试但担心被推销。',
    difficulty: 'easy',
    category: 'sales',
    required: true,
    status: 'not_started',
    openingLine: '你好，我看到你们门口说有新客优惠，能介绍一下吗？',
    persona: {
      name: '李女士',
      role: '预算敏感的新客',
      style: '友好但谨慎，会追问价格、隐性费用和是否马上决策。',
    },
    learnerRole: 'Salesperson',
    framework: 'prep',
    trainingPoints: ['快速建立信任', '清楚解释优惠边界', '用开放问题确认真实需求'],
  },
  {
    id: 'enterprise-demo-objection',
    title: '企业客户 Demo 异议',
    description: '客户认可价值，但担心上线周期、集成成本和团队采用率。',
    customerProfile: '中型企业部门负责人，有预算但需要降低实施风险。',
    difficulty: 'medium',
    category: 'sales',
    required: true,
    status: 'in_progress',
    score: 76,
    lastPracticedAt: '2026-07-12',
    openingLine: '方案听起来不错，但我们之前导入工具都很慢，你们怎么保证不会拖住团队？',
    persona: {
      name: '陈总',
      role: '企业采购决策人',
      style: '关注风险、落地成本和团队阻力，会要求具体案例与推进计划。',
    },
    learnerRole: 'Salesperson',
    framework: 'scqa',
    trainingPoints: ['识别真实反对点', '用证据化案例降低风险', '推进下一步共同计划'],
  },
  {
    id: 'refund-service-recovery',
    title: '退款与服务补救',
    description: '客户体验不佳要求退款，需要稳定情绪、确认事实并给出补救方案。',
    customerProfile: '已购买客户，情绪不满，认为服务承诺没有兑现。',
    difficulty: 'hard',
    category: 'customer_service',
    required: true,
    status: 'not_started',
    openingLine: '我上次体验很差，如果今天不给我一个说法，我就要求全额退款。',
    persona: {
      name: '王先生',
      role: '不满的已购客户',
      style: '情绪强烈，容易打断，只有感到被理解后才愿意讨论方案。',
    },
    learnerRole: 'Customer Success Specialist',
    framework: 'prep',
    trainingPoints: ['先接住情绪', '复述事实并确认缺口', '给出可执行补救选项'],
  },
  {
    id: 'renewal-price-negotiation',
    title: '续约价格谈判',
    description: '老客户准备续约，但拿竞品价格压价，要求额外折扣。',
    customerProfile: '年度续约客户，使用频率高，采购希望压低预算。',
    difficulty: 'expert',
    category: 'negotiation',
    required: false,
    status: 'completed',
    score: 88,
    lastPracticedAt: '2026-07-10',
    openingLine: '竞品给了我们更低的价格，如果你们不能再降 20%，我们很难续约。',
    persona: {
      name: '赵经理',
      role: '价格强势的采购经理',
      style: '强势、关注让步空间，会用竞品和预算压力测试底线。',
    },
    learnerRole: 'Account Manager',
    framework: 'pyramid',
    trainingPoints: ['守住价值锚点', '交换条件而不是单向让步', '明确 BATNA 和下一步'],
  },
  {
    id: 'recruiter-sales-interview',
    title: '销售岗位初筛',
    description: '候选人需要在短时间内讲清楚过往业绩、销售方法和动机。',
    customerProfile: '招聘方初筛，关注表达结构、业绩真实性和岗位匹配。',
    difficulty: 'medium',
    category: 'interview',
    required: false,
    status: 'not_started',
    openingLine: '请你先用一分钟介绍一下自己，重点讲讲最近一段销售经历。',
    persona: {
      name: '周 HR',
      role: '销售岗位招聘初筛官',
      style: '时间紧、问题直接，会追问业绩数字、客户类型和离职动机。',
    },
    learnerRole: 'Sales Candidate',
    framework: 'star',
    trainingPoints: ['用结果开场', '用 STAR 讲清楚关键案例', '解释动机和岗位匹配'],
  },
  {
    id: 'angry-vip-priority',
    title: 'VIP 优先级升级',
    description: '重点客户认为自己被忽视，要求立即升级优先级。',
    customerProfile: '高价值客户负责人，业务影响大，对响应速度非常敏感。',
    difficulty: 'hard',
    category: 'customer_service',
    required: false,
    status: 'not_started',
    openingLine: '我们是你们的大客户，这个问题拖了三天，为什么还没有优先处理？',
    persona: {
      name: '沈总',
      role: '高价值客户负责人',
      style: '压迫感强，要求承诺明确时间表，不接受含糊解释。',
    },
    learnerRole: 'Customer Success Manager',
    framework: 'scqa',
    trainingPoints: ['承认影响而不甩锅', '澄清优先级与责任人', '给出可追踪的恢复计划'],
  },
]

export function getScenarioTrainingCardById(scenarioId?: string | null): ScenarioTrainingCard | null {
  const normalizedId = scenarioId?.trim()
  if (!normalizedId) return null
  return scenarioTrainingCatalog.find((scenario) => scenario.id === normalizedId) ?? null
}

export function buildScenarioTrainingRouteState(scenario: ScenarioTrainingCard): ScenarioTrainingRouteState {
  return {
    source: 'scenario-training',
    scenarioTrainingId: scenario.id,
    scenarioTitle: scenario.title,
    scenarioDescription: scenario.description,
    scenarioCustomerProfile: scenario.customerProfile,
    scenarioOpeningLine: scenario.openingLine,
    scenarioPersonaName: scenario.persona.name,
    scenarioPersonaRole: scenario.persona.role,
    scenarioPersonaStyle: scenario.persona.style,
    scenarioLearnerRole: scenario.learnerRole,
    scenarioDifficulty: scenario.difficulty,
    scenarioCategory: scenario.category,
    scenarioRequired: scenario.required,
    scenarioTrainingPoints: [...scenario.trainingPoints],
  }
}

export function findScenarioTrainingIdBySession(
  progress: ScenarioTrainingProgress,
  trainingSessionId?: string | null,
): string | null {
  const normalizedSessionId = trainingSessionId?.trim()
  if (!normalizedSessionId) return null
  return Object.entries(progress).find(([, item]) => (
    item?.trainingSessionId === normalizedSessionId
  ))?.[0] ?? null
}

export function getScenarioTrainingProgress(scope?: ScenarioTrainingProgressScope): ScenarioTrainingProgress {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(progressStorageKey(scope))
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export function saveScenarioTrainingProgress(
  progress: ScenarioTrainingProgress,
  scope?: ScenarioTrainingProgressScope,
): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(progressStorageKey(scope), JSON.stringify(progress))
}

export function getScenarioScoreWeightTotal(dimensions: ScenarioScoreDimension[]): number {
  return dimensions
    .filter((dimension) => dimension.enabled)
    .reduce((total, dimension) => total + dimension.weight, 0)
}

export function areScenarioScoreWeightsValid(dimensions: ScenarioScoreDimension[]): boolean {
  return Math.abs(getScenarioScoreWeightTotal(dimensions) - 100) < 0.001
}

export function mergeScenarioTrainingProgress(
  catalog: ScenarioTrainingCard[],
  progress: ScenarioTrainingProgress,
): ScenarioTrainingCard[] {
  return catalog.map((scenario) => ({
    ...scenario,
    ...(progress[scenario.id] ?? {}),
  }))
}

function scoreForScenario(
  scenario: ScenarioTrainingCard,
  progress: ScenarioTrainingProgress,
): number | null {
  const item = progress[scenario.id]
  if (typeof item?.score === 'number') return item.score
  if (typeof scenario.score === 'number') return scenario.score
  return null
}

function dimensionForScenario(scenario: ScenarioTrainingCard): string {
  if (scenario.category === 'sales') return '价值表达'
  if (scenario.category === 'customer_service') return '情绪承接'
  if (scenario.category === 'negotiation') return '条件交换'
  if (scenario.category === 'workplace') return '向上汇报'
  return '结构表达'
}

export function buildScenarioLeaderboardRows(
  catalog: ScenarioTrainingCard[],
  progressByUser: Record<string, ScenarioTrainingProgress>,
  users: ScenarioLeaderboardUser[],
): ScenarioLeaderboardRow[] {
  const requiredScenarios = catalog.filter((scenario) => scenario.required)
  const rows = users.map((user) => {
    const progress = progressByUser[user.userId] ?? {}
    const scored = catalog
      .map((scenario) => ({ scenario, score: scoreForScenario(scenario, progress) }))
      .filter((item): item is { scenario: ScenarioTrainingCard; score: number } => typeof item.score === 'number')
    const completedRequired = requiredScenarios.filter((scenario) => (
      progress[scenario.id]?.status === 'completed'
      || (progress[scenario.id]?.status === undefined && scenario.status === 'completed')
    )).length
    const unfinishedRequired = requiredScenarios
      .filter((scenario) => (
        progress[scenario.id]?.status !== 'completed'
        && !(progress[scenario.id]?.status === undefined && scenario.status === 'completed')
      ))
      .map((scenario) => scenario.title)
    const pendingCount = catalog.filter((scenario) => (
      progress[scenario.id]?.scoreStatus === 'pending'
      || progress[scenario.id]?.status === 'in_progress'
    )).length
    const totalScore = scored.reduce((total, item) => total + item.score, 0)
    const averageScore = scored.length ? Math.round(totalScore / scored.length) : null
    const weakest = scored.length
      ? [...scored].sort((a, b) => a.score - b.score)[0].scenario
      : null

    return {
      userId: user.userId,
      name: user.name,
      teamId: user.teamId,
      teamName: user.teamName,
      roleName: user.roleName,
      rank: 0,
      completedRequired,
      totalRequired: requiredScenarios.length,
      completionRate: requiredScenarios.length ? Math.round((completedRequired / requiredScenarios.length) * 100) : 100,
      averageScore,
      totalScore,
      practicedCount: scored.length,
      pendingCount,
      unfinishedRequired,
      weakestDimension: weakest ? dimensionForScenario(weakest) : null,
    }
  })

  return rows
    .sort((a, b) => (
      (b.averageScore ?? -1) - (a.averageScore ?? -1)
      || b.completedRequired - a.completedRequired
      || a.name.localeCompare(b.name)
    ))
    .map((row, index) => ({ ...row, rank: index + 1 }))
}

function leaderboardNormalizeScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)))
}

function leaderboardRoundDelta(value: number): number {
  return Math.round(value)
}

function leaderboardScoreFromProgressItem(item?: ScenarioTrainingProgressItem): number | null {
  if (typeof item?.score === 'number') return leaderboardNormalizeScore(item.score)
  if (typeof item?.overallScore === 'number') {
    return leaderboardNormalizeScore(item.overallScore <= 5 ? item.overallScore * 20 : item.overallScore)
  }
  return null
}

function leaderboardScoreForScenario(
  scenario: ScenarioTrainingCard,
  progress: ScenarioTrainingProgress,
  useCatalogFallback: boolean,
): number | null {
  const item = progress[scenario.id]
  if (item) return leaderboardScoreFromProgressItem(item)
  if (useCatalogFallback && typeof scenario.score === 'number') return leaderboardNormalizeScore(scenario.score)
  if (useCatalogFallback && typeof scenario.overallScore === 'number') {
    return leaderboardNormalizeScore(scenario.overallScore <= 5 ? scenario.overallScore * 20 : scenario.overallScore)
  }
  return null
}

function leaderboardStatusForScenario(
  scenario: ScenarioTrainingCard,
  progress: ScenarioTrainingProgress,
  useCatalogFallback: boolean,
): ScenarioTrainingStatus {
  const item = progress[scenario.id]
  if (item?.status) return item.status
  return useCatalogFallback ? scenario.status : 'not_started'
}

function leaderboardLastPracticedAtForScenario(
  scenario: ScenarioTrainingCard,
  progress: ScenarioTrainingProgress,
  useCatalogFallback: boolean,
): string | undefined {
  const item = progress[scenario.id]
  if (item) return item.lastPracticedAt
  return useCatalogFallback ? scenario.lastPracticedAt : undefined
}

function leaderboardAverageScore(scores: number[]): number | null {
  if (scores.length === 0) return null
  return leaderboardNormalizeScore(scores.reduce((total, score) => total + score, 0) / scores.length)
}

function leaderboardTimestamp(value?: string): number {
  if (!value) return 0
  const time = new Date(value).getTime()
  return Number.isFinite(time) ? time : 0
}

function leaderboardLatestPracticedAt(values: Array<string | undefined>): string | undefined {
  return values
    .filter((value): value is string => Boolean(value))
    .sort((a, b) => leaderboardTimestamp(b) - leaderboardTimestamp(a))[0]
}

function leaderboardDimensionIdsForScenario(scenario: ScenarioTrainingCard): string[] {
  if (scenario.category === 'sales') {
    return ['trust_discovery', 'value_clarity', 'objection_handling', 'next_step']
  }
  if (scenario.category === 'customer_service') {
    return ['trust_discovery', 'objection_handling', 'next_step']
  }
  if (scenario.category === 'negotiation') {
    return ['value_clarity', 'objection_handling', 'next_step']
  }
  if (scenario.category === 'workplace') {
    return ['trust_discovery', 'value_clarity', 'next_step']
  }
  return ['trust_discovery', 'value_clarity']
}

interface ResolvedScenarioLeaderboardEntry {
  scenario: ScenarioTrainingCard
  status: ScenarioTrainingStatus
  score: number | null
  practiced: boolean
  lastPracticedAt?: string
}

interface ScenarioLeaderboardUserSummary extends ScenarioLeaderboardUser {
  entries: ResolvedScenarioLeaderboardEntry[]
  completedRequired: number
  totalRequired: number
  completionRate: number
  averageScore: number | null
  overallAverage: number | null
  practicedCount: number
  latestPracticedAt?: string
  unfinishedRequired: ScenarioLeaderboardScenarioRef[]
  isRanked: boolean
}

function resolveScenarioLeaderboardEntry(
  scenario: ScenarioTrainingCard,
  progress: ScenarioTrainingProgress,
  useCatalogFallback: boolean,
): ResolvedScenarioLeaderboardEntry {
  const status = leaderboardStatusForScenario(scenario, progress, useCatalogFallback)
  const score = leaderboardScoreForScenario(scenario, progress, useCatalogFallback)
  const lastPracticedAt = leaderboardLastPracticedAtForScenario(scenario, progress, useCatalogFallback)
  const practiced = status !== 'not_started' || score !== null || Boolean(lastPracticedAt)
  return { scenario, status, score, practiced, lastPracticedAt }
}

function buildScenarioLeaderboardUserSummary(
  catalog: ScenarioTrainingCard[],
  user: ScenarioLeaderboardProgressUser,
): ScenarioLeaderboardUserSummary {
  const entries = catalog.map((scenario) => (
    resolveScenarioLeaderboardEntry(scenario, user.progress, Boolean(user.useCatalogFallback))
  ))
  const requiredEntries = entries.filter((entry) => entry.scenario.required)
  const completedRequired = requiredEntries.filter((entry) => entry.status === 'completed').length
  const requiredScores = requiredEntries
    .filter((entry) => entry.status === 'completed' && entry.score !== null)
    .map((entry) => entry.score as number)
  const allScores = entries
    .filter((entry) => entry.score !== null)
    .map((entry) => entry.score as number)
  const unfinishedRequired = requiredEntries
    .filter((entry) => entry.status !== 'completed')
    .map((entry) => ({
      scenarioId: entry.scenario.id,
      title: entry.scenario.title,
    }))
  const practicedEntries = entries.filter((entry) => entry.practiced)
  const totalRequired = requiredEntries.length

  return {
    userId: user.userId,
    name: user.name,
    teamId: user.teamId,
    teamName: user.teamName,
    roleName: user.roleName,
    entries,
    completedRequired,
    totalRequired,
    completionRate: totalRequired ? Math.round((completedRequired / totalRequired) * 100) : 100,
    averageScore: leaderboardAverageScore(requiredScores),
    overallAverage: leaderboardAverageScore(allScores),
    practicedCount: practicedEntries.length,
    latestPracticedAt: leaderboardLatestPracticedAt(practicedEntries.map((entry) => entry.lastPracticedAt)),
    unfinishedRequired,
    isRanked: totalRequired > 0 && completedRequired >= totalRequired,
  }
}

function buildScenarioLeaderboardAbilityDimensions(
  entries: ResolvedScenarioLeaderboardEntry[],
): ScenarioLeaderboardAbilityDimension[] {
  const dimensionNames = new Map(defaultScenarioScoreDimensions.map((dimension) => [dimension.id, dimension.name]))
  const aggregate = new Map<string, { scores: number[]; scenarioTitles: Set<string> }>()

  entries.forEach((entry) => {
    if (entry.score === null) return
    leaderboardDimensionIdsForScenario(entry.scenario).forEach((dimensionId) => {
      const current = aggregate.get(dimensionId) ?? { scores: [], scenarioTitles: new Set<string>() }
      current.scores.push(entry.score as number)
      current.scenarioTitles.add(entry.scenario.title)
      aggregate.set(dimensionId, current)
    })
  })

  return [...aggregate.entries()]
    .map(([dimensionId, item]) => {
      const avg = leaderboardAverageScore(item.scores) ?? 0
      return {
        dimensionId,
        name: dimensionNames.get(dimensionId) ?? dimensionId,
        averageScore: avg,
        isWeak: avg < 70,
        sampleCount: item.scores.length,
        scenarioTitles: [...item.scenarioTitles],
      }
    })
    .sort((a, b) => a.averageScore - b.averageScore || a.name.localeCompare(b.name))
}

function buildScenarioLeaderboardScenarioAverages(
  catalog: ScenarioTrainingCard[],
  summaries: ScenarioLeaderboardUserSummary[],
): ScenarioLeaderboardScenarioAverage[] {
  return catalog
    .map((scenario) => {
      const scores = summaries
        .map((summary) => summary.entries.find((entry) => entry.scenario.id === scenario.id)?.score ?? null)
        .filter((score): score is number => typeof score === 'number')
      const avg = leaderboardAverageScore(scores)
      if (avg === null) return null
      return {
        scenarioId: scenario.id,
        title: scenario.title,
        difficulty: scenario.difficulty,
        category: scenario.category,
        required: scenario.required,
        averageScore: avg,
        participantCount: scores.length,
      }
    })
    .filter((item): item is ScenarioLeaderboardScenarioAverage => Boolean(item))
    .sort((a, b) => a.averageScore - b.averageScore || a.title.localeCompare(b.title))
}

export function buildScenarioLeaderboardSummary(
  catalog: ScenarioTrainingCard[],
  users: ScenarioLeaderboardProgressUser[],
  currentUserId?: string | null,
): ScenarioLeaderboardSummary {
  const summaries = users.map((user) => buildScenarioLeaderboardUserSummary(catalog, user))
  const ranks = summaries
    .filter((summary) => summary.isRanked)
    .sort((a, b) => (
      (b.averageScore ?? -1) - (a.averageScore ?? -1)
      || b.completedRequired - a.completedRequired
      || a.name.localeCompare(b.name)
    ))
    .map<ScenarioLeaderboardRankRow>((summary, index) => ({
      userId: summary.userId,
      name: summary.name,
      teamId: summary.teamId,
      teamName: summary.teamName,
      roleName: summary.roleName,
      rank: index + 1,
      averageScore: summary.averageScore,
      completedRequired: summary.completedRequired,
      totalRequired: summary.totalRequired,
      completionRate: summary.completionRate,
      practicedCount: summary.practicedCount,
      latestPracticedAt: summary.latestPracticedAt,
      isCurrentUser: summary.userId === currentUserId,
    }))
  const unfinished = summaries
    .filter((summary) => !summary.isRanked)
    .sort((a, b) => (
      b.completionRate - a.completionRate
      || b.practicedCount - a.practicedCount
      || a.name.localeCompare(b.name)
    ))
    .map<ScenarioLeaderboardUnfinishedRow>((summary) => ({
      userId: summary.userId,
      name: summary.name,
      teamId: summary.teamId,
      teamName: summary.teamName,
      roleName: summary.roleName,
      averageScore: summary.overallAverage,
      completedRequired: summary.completedRequired,
      totalRequired: summary.totalRequired,
      completionRate: summary.completionRate,
      practicedCount: summary.practicedCount,
      latestPracticedAt: summary.latestPracticedAt,
      unfinishedRequired: summary.unfinishedRequired,
      status: summary.practicedCount > 0 ? 'in_progress' : 'not_started',
      isCurrentUser: summary.userId === currentUserId,
    }))
  const scenarioAverages = buildScenarioLeaderboardScenarioAverages(catalog, summaries)
  const scenarioAverageMap = new Map(scenarioAverages.map((scenario) => [scenario.scenarioId, scenario.averageScore]))
  const personalSummary = summaries.find((summary) => summary.userId === currentUserId) ?? summaries[0] ?? null
  const personalRank = personalSummary
    ? ranks.find((row) => row.userId === personalSummary.userId)?.rank ?? null
    : null
  const personal = personalSummary
    ? {
      user: {
        userId: personalSummary.userId,
        name: personalSummary.name,
        teamId: personalSummary.teamId,
        teamName: personalSummary.teamName,
        roleName: personalSummary.roleName,
      },
      status: personalSummary.isRanked
        ? 'ranked'
        : personalSummary.practicedCount > 0
          ? 'partial'
          : 'unstart',
      rank: personalRank,
      averageScore: personalSummary.averageScore,
      overallAverage: personalSummary.overallAverage,
      completedRequired: personalSummary.completedRequired,
      totalRequired: personalSummary.totalRequired,
      completionRate: personalSummary.completionRate,
      practicedCount: personalSummary.practicedCount,
      latestPracticedAt: personalSummary.latestPracticedAt,
      unfinishedRequired: personalSummary.unfinishedRequired,
      abilityProfile: buildScenarioLeaderboardAbilityDimensions(personalSummary.entries),
      scenarioStats: personalSummary.entries.map((entry) => {
        const teamAverage = scenarioAverageMap.get(entry.scenario.id) ?? null
        return {
          scenarioId: entry.scenario.id,
          title: entry.scenario.title,
          difficulty: entry.scenario.difficulty,
          category: entry.scenario.category,
          required: entry.scenario.required,
          status: entry.status,
          score: entry.score,
          teamAverage,
          gap: entry.score !== null && teamAverage !== null
            ? leaderboardRoundDelta(entry.score - teamAverage)
            : null,
          practiced: entry.practiced,
          lastPracticedAt: entry.lastPracticedAt,
        }
      }),
    } satisfies ScenarioLeaderboardPersonalOverview
    : null
  const rankScores = ranks
    .map((row) => row.averageScore)
    .filter((score): score is number => typeof score === 'number')

  return {
    totalRequired: catalog.filter((scenario) => scenario.required).length,
    totalUsers: summaries.length,
    team: {
      participants: summaries.filter((summary) => summary.practicedCount > 0).length,
      ranked: ranks.length,
      unfinishedActive: unfinished.filter((row) => row.practicedCount > 0).length,
      unfinishedAll: unfinished.length,
      teamAverage: leaderboardAverageScore(rankScores),
      ranks,
      unfinished,
      weakDimensions: buildScenarioLeaderboardAbilityDimensions(summaries.flatMap((summary) => summary.entries)),
      scenarioAverages,
    },
    personal,
  }
}

function progressTimestamp(item?: ScenarioTrainingProgressItem): number {
  if (!item?.lastPracticedAt) return 0
  const time = new Date(item.lastPracticedAt).getTime()
  return Number.isFinite(time) ? time : 0
}

function mergeProgressItem(
  primary: ScenarioTrainingProgressItem,
  fallback?: ScenarioTrainingProgressItem,
): ScenarioTrainingProgressItem {
  return {
    ...fallback,
    ...primary,
    score: primary.score ?? fallback?.score,
    scoreStatus: primary.scoreStatus ?? fallback?.scoreStatus,
    overallScore: primary.overallScore ?? fallback?.overallScore,
    evaluationId: primary.evaluationId ?? fallback?.evaluationId,
    lastPracticedAt: primary.lastPracticedAt ?? fallback?.lastPracticedAt,
    userId: primary.userId ?? fallback?.userId,
    teamId: primary.teamId ?? fallback?.teamId,
    trainingSessionId: primary.trainingSessionId ?? fallback?.trainingSessionId,
    reportId: primary.reportId ?? fallback?.reportId,
    scoreId: primary.scoreId ?? fallback?.scoreId,
    failureReason: primary.failureReason ?? fallback?.failureReason,
  }
}

export function mergeScenarioTrainingProgressRecords(
  current: ScenarioTrainingProgress,
  incoming: ScenarioTrainingProgress,
): ScenarioTrainingProgress {
  const merged: ScenarioTrainingProgress = { ...current }
  Object.entries(incoming).forEach(([scenarioId, next]) => {
    if (!next) return
    const existing = merged[scenarioId]
    merged[scenarioId] = !existing || progressTimestamp(next) >= progressTimestamp(existing)
      ? mergeProgressItem(next, existing)
      : mergeProgressItem(existing, next)
  })
  return merged
}

export function markScenarioTrainingStarted(
  progress: ScenarioTrainingProgress,
  scenarioId: string,
  trainingSessionId?: string,
  scope?: ScenarioTrainingProgressScope | Date,
  now = new Date(),
): ScenarioTrainingProgress {
  const actualScope = scope instanceof Date ? undefined : scope
  const actualNow = scope instanceof Date ? scope : now
  return {
    ...progress,
    [scenarioId]: {
      ...progress[scenarioId],
      status: 'in_progress',
      lastPracticedAt: actualNow.toISOString(),
      userId: actualScope?.userId ?? progress[scenarioId]?.userId,
      teamId: actualScope?.teamId ?? progress[scenarioId]?.teamId,
      scoreStatus: 'pending',
      trainingSessionId,
    },
  }
}

export function markScenarioTrainingCompleted(
  progress: ScenarioTrainingProgress,
  scenarioId: string,
  options: {
    trainingSessionId?: string
    reportId?: string | number | null
    scoreId?: string | number | null
    score?: number | null
    scoreStatus?: 'ready' | 'pending'
    overallScore?: number | null
    evaluationId?: number | null
    scope?: ScenarioTrainingProgressScope
    completedAt?: string | Date
  } = {},
): ScenarioTrainingProgress {
  const completedAt = options.completedAt instanceof Date
    ? options.completedAt.toISOString()
    : options.completedAt || new Date().toISOString()

  return {
    ...progress,
    [scenarioId]: {
      ...progress[scenarioId],
      status: 'completed',
      score: typeof options.score === 'number' ? options.score : progress[scenarioId]?.score,
      scoreStatus: options.scoreStatus ?? progress[scenarioId]?.scoreStatus,
      overallScore: typeof options.overallScore === 'number' ? options.overallScore : progress[scenarioId]?.overallScore,
      evaluationId: typeof options.evaluationId === 'number' ? options.evaluationId : progress[scenarioId]?.evaluationId,
      lastPracticedAt: completedAt,
      userId: options.scope?.userId ?? progress[scenarioId]?.userId,
      teamId: options.scope?.teamId ?? progress[scenarioId]?.teamId,
      trainingSessionId: options.trainingSessionId ?? progress[scenarioId]?.trainingSessionId,
      reportId: options.reportId == null ? progress[scenarioId]?.reportId : String(options.reportId),
      scoreId: options.scoreId == null ? progress[scenarioId]?.scoreId : String(options.scoreId),
    },
  }
}

export function buildScenarioTrainingTaskConfig(scenario: ScenarioTrainingCard): TrainingTaskConfigDTO {
  const dimensionWeights = getDefaultDimensionWeights(scenario.category)
  const rubricWeights = Object.fromEntries(
    dimensionWeights.map((item) => [item.dimensionId, item.weight / 100]),
  )

  return {
    role: scenario.learnerRole,
    level: scenario.difficulty === 'expert' ? 'expert' : scenario.difficulty,
    tech_stack: [
      scenario.title,
      scenario.customerProfile,
      `category:${scenario.category}`,
      `opening:${scenario.openingLine}`,
    ],
    question_type_ratios: {
      behavioral: scenario.category === 'interview' ? 45 : 20,
      craft: scenario.category === 'negotiation' ? 35 : 45,
      pressure: scenario.difficulty === 'easy' ? 20 : 35,
    },
    question_count: scenario.required ? 8 : 6,
    framework: scenario.framework,
    difficulty: difficultyToTrainingStudio[scenario.difficulty],
    category: categoryToTrainingStudio[scenario.category],
    rubric_weights: rubricWeights,
    metadata: {
      source: 'scenario_training',
      scenario_training: {
        id: scenario.id,
        title: scenario.title,
        required: scenario.required,
        category: scenario.category,
        difficulty: scenario.difficulty,
        dimension_weights: dimensionWeights,
      },
    },
  }
}

export function buildScenarioTrainingPrompt(
  scenario: ScenarioTrainingCard,
  mode: TrainingMode,
): string {
  return [
    `Scenario training: ${scenario.title}`,
    '',
    scenario.description,
    '',
    `Customer profile: ${scenario.customerProfile}`,
    `Required drill: ${scenario.required ? 'yes' : 'no'}`,
    `Card difficulty: ${scenario.difficulty}`,
    `Practice mode: ${mode}`,
    '',
    `AI customer opening line: ${scenario.openingLine}`,
    '',
    'Instructions for the AI customer:',
    `- In your first response, start with this exact opening line: ${scenario.openingLine}`,
    '- Stay in character as the customer, buyer, interviewer, or counterpart described above.',
    '- This is not a cooperative demo. You have your own interests, skepticism, and decision threshold.',
    '- Speak in first person with natural short turns. Usually reply in 30-120 Chinese characters.',
    '- You may occasionally include one brief physical or emotional cue in parentheses, such as （皱眉） or （停顿一下）, but do not write a script.',
    '- Do not reveal all needs, budget, objections, or bottom lines at once. Disclose them gradually as the learner earns trust.',
    '- If the learner is vague, pushy, scripted, exaggerates, or dodges your concern, ask for evidence, challenge, compare alternatives, or show frustration.',
    '- If the learner understands you, gives grounded answers, stays natural, and handles your real concern, soften gradually without instantly agreeing.',
    '- Never explain training rules, never score the learner, never give coaching advice, and never add markdown or speaker prefixes.',
    `- Difficulty behavior: ${scenarioDifficultyBehavior[scenario.difficulty]}`,
    '- Push naturally on the training points, and make the learner demonstrate the target behavior.',
  ].join('\n')
}

export function buildScenarioTrainingBattlePayload(
  scenario: ScenarioTrainingCard,
  mode: TrainingMode,
) {
  const battleDifficulty = scenario.difficulty === 'easy'
    ? 'easy'
    : scenario.difficulty === 'medium'
      ? 'normal'
      : 'hard'

  return {
    persona_name: scenario.persona.name,
    persona_role: scenario.persona.role,
    persona_style: [
      scenario.persona.style,
      'Speak like a real counterpart: short, spoken, specific, and never as a coach or scoring judge.',
      `Response mode: ${mode}.`,
      `First turn opening line: ${scenario.openingLine}`,
    ].join('\n'),
    scenario_context: buildScenarioTrainingPrompt(scenario, mode),
    selected_training_points: scenario.trainingPoints,
    difficulty: battleDifficulty,
  } as const
}
