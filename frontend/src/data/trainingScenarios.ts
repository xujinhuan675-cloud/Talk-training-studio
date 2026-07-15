import type { TrainingMode } from '../services/trainingMode'
import type { TrainingTaskConfigDTO } from '../services/trainingSession'

export type ScenarioTrainingDifficulty = 'easy' | 'medium' | 'hard' | 'expert'
export type ScenarioTrainingCategory = 'sales' | 'customer_service' | 'negotiation' | 'interview'
export type ScenarioTrainingStatus = 'not_started' | 'in_progress' | 'completed'

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
}

export type ScenarioTrainingProgress = Partial<Record<string, ScenarioTrainingProgressItem>>

const PROGRESS_STORAGE_KEY = 'talkwise.scenarioTraining.progress.v1'

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
}

const scenarioDifficultyBehavior: Record<ScenarioTrainingDifficulty, string> = {
  easy: 'Keep 1-2 normal concerns, listen when the learner answers clearly, but do not agree immediately.',
  medium: 'Hold clear concerns from the profile. You need grounded, non-pushy answers before you soften.',
  hard: 'Actively raise objections, compare alternatives, test price/value claims, and push back on vague or scripted answers.',
  expert: 'Stay highly guarded. Use probing, reversals, price pressure, emotional doubt, and only soften gradually after several strong turns.',
}

export const scenarioTrainingCatalog: ScenarioTrainingCard[] = [
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

export function mergeScenarioTrainingProgress(
  catalog: ScenarioTrainingCard[],
  progress: ScenarioTrainingProgress,
): ScenarioTrainingCard[] {
  return catalog.map((scenario) => ({
    ...scenario,
    ...(progress[scenario.id] ?? {}),
  }))
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
    metadata: {
      source: 'scenario_training',
      scenario_training: {
        id: scenario.id,
        title: scenario.title,
        required: scenario.required,
        category: scenario.category,
        difficulty: scenario.difficulty,
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
