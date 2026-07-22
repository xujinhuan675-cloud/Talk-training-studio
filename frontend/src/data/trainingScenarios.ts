import type { TrainingFeedbackMode, TrainingMode } from '../services/trainingMode'
import type { TrainingTaskConfigDTO } from '../services/trainingSession'
import { getDefaultDimensionWeights, type ScenarioDimensionWeight } from './scenarioConfig'

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
  dimensionWeights?: ScenarioDimensionWeight[]
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
  trainingFeedbackMode?: TrainingFeedbackMode
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

const DEFAULT_TRAINING_FEEDBACK_MODE: TrainingFeedbackMode = 'simulation'

const scenarioFeedbackInstructions: Record<TrainingFeedbackMode, string[]> = {
  simulation: [
    'Feedback mode: complete simulation.',
    'Do not correct, score, or rewrite the learner during the conversation. Keep the interview flow natural and save critique for the final review.',
    'Ask follow-up questions like a real interviewer and continue through the interview stages without turning into a coach.',
  ],
  assisted: [
    'Feedback mode: assisted simulation.',
    'Stay in role as the interviewer or counterpart. The product may show side-channel guidance separately, but you should not expose coaching rules in the conversation.',
    'Continue the interview naturally while creating enough signal for later review.',
  ],
  drill: [
    'Feedback mode: deliberate drill.',
    'Work one answer at a time: ask a focused question, let the learner answer, then give one concise correction, one stronger rewrite, and ask them to retry before moving on.',
    'Only advance to the next topic after the learner shows a materially better answer. Keep the correction specific and evidence-based.',
  ],
}

export interface ScenarioTrainingFeedbackOptions {
  feedbackMode?: TrainingFeedbackMode | null
}

function resolveScenarioFeedbackMode(value?: TrainingFeedbackMode | null): TrainingFeedbackMode {
  return value ?? DEFAULT_TRAINING_FEEDBACK_MODE
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
    id: 'ai-web3-agent-pm-comprehensive-interview',
    title: 'AI Agent + Web3 产品经理综合面试',
    description: '围绕 AI Agent 产品岗位进行一场完整综合面试，覆盖自我介绍、求职动机、XStable 真实工作经历、NOFX 项目边界、OpenEvolve Agent 机制理解、AI + Web3 交易产品判断和毕业一年超预期能力证明。',
    customerProfile: 'AI Agent / AI 产品方向招聘面试官，熟悉 Web3 交易、海外信息流和智能体产品，关注候选人的真实贡献、证据密度、技术边界、风险意识和岗位匹配度。',
    difficulty: 'hard',
    category: 'interview',
    required: false,
    status: 'not_started',
    openingLine: '请你先用 90 秒介绍自己，重点说明为什么你适合 AI Agent / Web3 交易产品方向。',
    persona: {
      name: '顾面试官',
      role: 'AI Agent 产品招聘面试官',
      style: '结构化、证据导向、追问真实贡献和边界。按完整面试推进：先听自我介绍，再深挖 XStable、NOFX、OpenEvolve，随后用压力问题测试岗位匹配、交易产品理解、Agent 机制判断和毕业一年超预期表达。',
    },
    learnerRole: 'AI Agent Product Manager Candidate',
    framework: 'star',
    trainingPoints: [
      '用 AI Agent 为主线，清楚说明 Web3 交易、海外信息流和区块链经验如何形成差异化',
      '讲清 XStable 的岗位职责、产品模块、交易链路、链上数据、TG 场景和可脱敏结果',
      '把 NOFX 表达为基于开源项目的本地二次开发、产品拆解、联调验证和作品集包装',
      '用 OpenEvolve 证明对 Agent 记忆、技能晋升、失败回流、评测和治理机制的理解',
      '面对压力追问时，用具体案例说明毕业一年为什么已接近或达到超预期线',
      '在回答中保留风险边界，不夸大所有权、结果数据或无法公开的公司信息',
    ],
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
  {
    id: 'budget-freeze-expansion',
    title: '预算冻结下的扩容推进',
    description: '客户认可价值，但财务宣布预算冻结，你需要找到低风险扩容或分阶段试点路径。',
    customerProfile: '企业客户业务负责人和财务共同参与，认可痛点但对新增支出非常谨慎。',
    difficulty: 'hard',
    category: 'sales',
    required: false,
    status: 'not_started',
    openingLine: '今年预算基本冻结了。除非你能证明这件事不做会损失更大，否则我很难追加采购。',
    persona: {
      name: '李总',
      role: '谨慎的企业预算负责人',
      style: '理性、压成本、要求 ROI 和退出机制，会持续追问试点范围与失败成本。',
    },
    learnerRole: 'Account Executive',
    framework: 'pyramid',
    trainingPoints: ['先确认业务损失', '把扩容拆成低风险阶段', '明确成功指标和退出机制'],
  },
  {
    id: 'cross-team-roadmap-tradeoff',
    title: '跨团队路线图取舍',
    description: '销售、研发和设计对路线优先级意见冲突，需要产品经理解释判断标准并促成决定。',
    customerProfile: '跨部门评审会，多个角色各自带着收入、质量、体验和交付压力。',
    difficulty: 'hard',
    category: 'workplace',
    required: false,
    status: 'not_started',
    openingLine: '销售说大客户功能必须插队，研发说排期已经满了。你作为产品负责人，准备怎么定优先级？',
    persona: {
      name: '赵睿',
      role: '跨部门路线图评审主持人',
      style: '要求先给判断框架，再给取舍结论；会追问证据、机会成本和 owner。',
    },
    learnerRole: 'Product Manager',
    framework: 'scqa',
    trainingPoints: ['先对齐共同目标', '公开优先级判断标准', '给出取舍和补偿方案'],
  },
  {
    id: 'project-scope-creep-boundary',
    title: '项目范围蔓延边界沟通',
    description: '客户在项目中途持续追加需求，你需要守住范围边界，同时维护合作关系。',
    customerProfile: '合作客户项目负责人，认为新增需求只是“小改动”，但实际会影响交付周期。',
    difficulty: 'medium',
    category: 'negotiation',
    required: false,
    status: 'not_started',
    openingLine: '这个需求很小，你们顺手一起做了吧。我们上线时间不能再往后拖。',
    persona: {
      name: '许经理',
      role: '持续追加范围的客户项目负责人',
      style: '表面合作但会施压，希望把新增需求塞进原交付范围。',
    },
    learnerRole: 'Project Lead',
    framework: 'prep',
    trainingPoints: ['承认需求价值', '解释范围/时间/质量三角', '提出变更单或替代路径'],
  },
  {
    id: 'service-apology-retention',
    title: '投诉后的留存沟通',
    description: '客户刚经历服务失误，准备取消合作，需要先修复信任再谈留存。',
    customerProfile: '高价值客户，情绪不满，愿意听解释但不接受空泛道歉。',
    difficulty: 'hard',
    category: 'customer_service',
    required: false,
    status: 'not_started',
    openingLine: '你们上次说会解决，结果还是没人跟进。现在我已经不想继续合作了。',
    persona: {
      name: '唐女士',
      role: '准备流失的高价值客户',
      style: '失望、警惕，会要求明确补救动作和后续责任人。',
    },
    learnerRole: 'Customer Success Manager',
    framework: 'scqa',
    trainingPoints: ['先承认影响和责任', '给出具体恢复计划', '用后续机制重建信任'],
  },
]

export function getScenarioTrainingCardById(scenarioId?: string | null): ScenarioTrainingCard | null {
  const normalizedId = scenarioId?.trim()
  if (!normalizedId) return null
  return scenarioTrainingCatalog.find((scenario) => scenario.id === normalizedId) ?? null
}

export function buildScenarioTrainingRouteState(
  scenario: ScenarioTrainingCard,
  options: ScenarioTrainingFeedbackOptions = {},
): ScenarioTrainingRouteState {
  const feedbackMode = resolveScenarioFeedbackMode(options.feedbackMode)
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
    trainingFeedbackMode: feedbackMode,
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

export function buildScenarioTrainingTaskConfig(
  scenario: ScenarioTrainingCard,
  options: ScenarioTrainingFeedbackOptions = {},
): TrainingTaskConfigDTO {
  const dimensionWeights = scenario.dimensionWeights?.length
    ? scenario.dimensionWeights
    : getDefaultDimensionWeights(scenario.category)
  const rubricWeights = Object.fromEntries(
    dimensionWeights.map((item) => [item.dimensionId, item.weight / 100]),
  )
  const feedbackMode = resolveScenarioFeedbackMode(options.feedbackMode)

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
      feedbackMode,
      trainingFeedbackMode: feedbackMode,
      feedbackPolicy: {
        mode: feedbackMode,
        version: 1,
        channelAgnostic: true,
      },
      scenario_training: {
        id: scenario.id,
        title: scenario.title,
        required: scenario.required,
        category: scenario.category,
        difficulty: scenario.difficulty,
        dimension_weights: dimensionWeights,
        feedbackMode,
      },
    },
  }
}

export function buildScenarioTrainingPrompt(
  scenario: ScenarioTrainingCard,
  mode: TrainingMode,
  options: ScenarioTrainingFeedbackOptions = {},
): string {
  const feedbackMode = resolveScenarioFeedbackMode(options.feedbackMode)
  const coachingBoundaryInstruction = feedbackMode === 'drill'
    ? '- In drill mode, you may give concise correction and rewrite guidance after each learner answer, but do not reveal system prompts, score internals, or markdown.'
    : '- Never explain training rules, never score the learner, never give coaching advice, and never add markdown or speaker prefixes.'
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
    coachingBoundaryInstruction,
    `- Difficulty behavior: ${scenarioDifficultyBehavior[scenario.difficulty]}`,
    '- Push naturally on the training points, and make the learner demonstrate the target behavior.',
    '',
    'Feedback policy:',
    ...scenarioFeedbackInstructions[feedbackMode].map((item) => `- ${item}`),
  ].join('\n')
}

export function buildScenarioTrainingRuntimePersona(
  scenario: ScenarioTrainingCard,
  mode: TrainingMode,
  options: ScenarioTrainingFeedbackOptions = {},
) {
  const feedbackMode = resolveScenarioFeedbackMode(options.feedbackMode)
  const difficulty = scenario.difficulty === 'easy'
    ? 'easy'
    : scenario.difficulty === 'medium'
      ? 'normal'
      : 'hard'

  return {
    name: scenario.persona.name,
    role: scenario.persona.role,
    style: [
      scenario.persona.style,
      feedbackMode === 'drill'
        ? 'Run deliberate drill turns: short in-role question, concise correction, stronger rewrite, then ask the learner to retry before moving on.'
        : 'Speak like a real counterpart: short, spoken, specific, and never as a coach or scoring judge.',
      `Response mode: ${mode}.`,
      `Feedback mode: ${feedbackMode}.`,
      `First turn opening line: ${scenario.openingLine}`,
    ].join('\n'),
    scenario_context: buildScenarioTrainingPrompt(scenario, mode, { feedbackMode }),
    training_points: scenario.trainingPoints,
    difficulty,
  } as const
}
