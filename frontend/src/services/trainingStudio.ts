import { getAuthRequestHeaders } from './auth'
import type { Translate, TranslationKey, TranslationParams } from '../i18n'
import {
  DEFAULT_TRAINING_REPLY_LANGUAGE,
  formatTrainingReplyLanguagePromptValue,
} from '../data/trainingReplyLanguages'

export type TrainingScenario = 'interview' | 'sales' | 'negotiation' | 'workplace' | 'product_management'
export type TrainingDifficulty = 'easy' | 'medium' | 'hard'
export type ExpressionFramework = 'prep' | 'star' | 'scqa' | 'pyramid'
export type TrainingLevel = 'intern' | 'junior' | 'mid' | 'senior' | 'staff' | 'manager'
export type TrainingReplyLanguage = string
export type InterviewRolePresetId =
  | 'recruiter_screen'
  | 'hiring_manager'
  | 'product_case_interviewer'
  | 'cross_functional_interviewer'
  | 'bar_raiser'
export type InterviewScenarioPresetId =
  | 'self_intro_pitch'
  | 'resume_deep_dive'
  | 'product_sense_case'
  | 'metrics_growth_case'
  | 'behavioral_leadership'
  | 'cross_functional_round'
  | 'offer_negotiation'
export type ProductRolePresetId = 'core_pm' | 'growth_pm' | 'platform_pm' | 'ai_pm'
export type ProductScenarioPresetId =
  | 'roadmap_prioritization'
  | 'prd_review'
  | 'launch_risk_review'
  | 'user_feedback_triage'
  | 'executive_update'
  | 'stakeholder_conflict'

export interface QuestionMix {
  behavioral: number
  technical: number
  pressure: number
}

export interface TrainingStudioConfig {
  scenario: TrainingScenario
  interviewRolePreset: InterviewRolePresetId | ''
  interviewScenarioPreset: InterviewScenarioPresetId | ''
  productRolePreset: ProductRolePresetId | ''
  productScenarioPreset: ProductScenarioPresetId | ''
  difficulty: TrainingDifficulty
  framework: ExpressionFramework
  role: string
  level: TrainingLevel
  techStack: string
  questionMix: QuestionMix
  questionCount: number
  replyLanguage: TrainingReplyLanguage
}

export interface VideoAnswerUploadResult {
  filename: string
  url: string
  mimeType: string
  size: number
}

export interface VideoAnswerUploadRequest {
  trainingSessionId: string
  roomId: number
  filename?: string
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const TRAINING_STUDIO_API_BASE = '/api/v1/training-studio'
const REALTIME_CAPABILITIES_API = `${TRAINING_STUDIO_API_BASE}/realtime/capabilities`

export interface RealtimeReadinessIssue {
  code?: string
  message?: string
  phase?: string
  provider?: string
  feature?: string
  modules?: string[]
  missingEnv?: string[]
  metadata?: Record<string, unknown>
}

export interface PipecatRealtimeReadiness {
  ready: boolean
  status: string
  checkedAt?: string
  required?: {
    transport?: string
    features?: Record<string, string>
    env?: string[]
  }
  blockingReasons?: RealtimeReadinessIssue[]
}

export interface PipecatProviderCatalogChannelSummary {
  count: number
  providers: string[]
  runtimeIntegrated: string[]
  inventoryOnly: string[]
}

export interface PipecatProviderCatalogSummary {
  schemaVersion: number
  packageVersion?: string | null
  source?: string
  channels: Record<string, PipecatProviderCatalogChannelSummary>
}

export interface PipecatRealtimeCapability {
  available: boolean
  coreAvailable: boolean
  websocketAvailable: boolean
  vadAvailable: boolean
  sttAvailable: boolean
  ttsAvailable: boolean
  llmAvailable: boolean
  turnDetectionAvailable: boolean
  missingModules: string[]
  optionalMissingModules: string[]
  error: string | null
  readyForCall: boolean
  readiness?: PipecatRealtimeReadiness
  errors?: RealtimeReadinessIssue[]
  providerCatalogSummary?: PipecatProviderCatalogSummary
  sourceSnapshot?: Record<string, unknown>
}

export interface RealtimeCapabilities {
  pipecat: PipecatRealtimeCapability
}

export type TrainingStudioReadinessStatus = 'ready' | 'warning' | 'blocked' | 'unknown'

export type RuntimeCapabilityKind = 'provider' | 'model' | 'agent' | 'tool' | 'mcp_server' | 'runtime' | string
export type RuntimeCapabilityStatus =
  | 'available'
  | 'ready'
  | 'warning'
  | 'blocked'
  | 'missingDependency'
  | 'unavailable'
  | 'disabled'
  | 'unknown'
  | string

export interface RuntimeCapabilityReadiness {
  ready?: boolean
  status?: RuntimeCapabilityStatus
  blockingReasons?: RealtimeReadinessIssue[]
  warnings?: RealtimeReadinessIssue[]
  errors?: RealtimeReadinessIssue[]
  [key: string]: unknown
}

export interface RuntimeCapabilityRegistryItem {
  id?: string
  kind?: RuntimeCapabilityKind
  name?: string
  provider?: string | null
  source?: string | null
  status?: RuntimeCapabilityStatus
  enabled?: boolean
  ready?: boolean
  configured?: boolean | null
  scopes?: string[]
  required_roles?: string[]
  requiredRoles?: string[]
  tags?: string[]
  readiness?: RuntimeCapabilityReadiness | null
  blockingReasons?: RealtimeReadinessIssue[]
  errors?: RealtimeReadinessIssue[]
  metadata?: Record<string, unknown>
  [key: string]: unknown
}

export interface RuntimeCapabilityRegistry {
  provider?: string
  version?: number
  capabilities?: RuntimeCapabilityRegistryItem[]
  by_kind?: Record<string, RuntimeCapabilityRegistryItem[]>
  byKind?: Record<string, RuntimeCapabilityRegistryItem[]>
  [key: string]: unknown
}

export interface TrainingStudioModelCapabilityInput {
  provider?: string | null
  providerLabel?: string | null
  model?: string | null
  modelLabel?: string | null
  capabilities?: string[] | null
  disabled?: boolean
  isDefault?: boolean
  wireApi?: string | null
  endpoint?: string | null
  disabledReason?: string | null
}

export interface TrainingStudioCapabilityMetric {
  label: string
  value: string
}

export interface TrainingStudioCapabilityItem {
  key: string
  label: string
  status: TrainingStudioReadinessStatus
  detail: string
  tags: string[]
  metrics: TrainingStudioCapabilityMetric[]
}

export interface TrainingStudioCapabilityReadiness {
  overallStatus: TrainingStudioReadinessStatus
  foundation: TrainingStudioCapabilityItem[]
  providerModel: TrainingStudioCapabilityItem
  realtime: TrainingStudioCapabilityItem
  agentMcp: TrainingStudioCapabilityItem
  modelCounts: {
    providers: number
    models: number
    selectableModels: number
    toolCapableModels: number
    mcpCapableModels: number
  }
  realtimeCounts: {
    pipecatFeatures: number
    pipecatReadyFeatures: number
    blockingIssues: number
  }
}

export interface BuildTrainingStudioCapabilityReadinessInput {
  realtimeCapabilities?: RealtimeCapabilities | null
  modelChoices?: TrainingStudioModelCapabilityInput[] | null
  capabilityRegistry?: RuntimeCapabilityRegistry | null
}

interface LocalizedOption<T extends string> {
  value: T
  labelKey: TranslationKey
  descKey?: TranslationKey
  fallbackLabel: string
  fallbackDesc?: string
}

export interface ProductRolePreset extends LocalizedOption<ProductRolePresetId> {
  roleKey: TranslationKey
  focusKey: TranslationKey
  level: TrainingLevel
  questionMix: QuestionMix
  fallbackRole: string
  fallbackFocus: string
}

export interface InterviewRolePreset extends LocalizedOption<InterviewRolePresetId> {
  roleKey: TranslationKey
  focusKey: TranslationKey
  level: TrainingLevel
  questionMix: QuestionMix
  fallbackRole: string
  fallbackFocus: string
}

export interface ProductScenarioPreset extends LocalizedOption<ProductScenarioPresetId> {
  focusKey: TranslationKey
  personaNameKey: TranslationKey
  personaRoleKey: TranslationKey
  personaStyleKey: TranslationKey
  framework: ExpressionFramework
  difficulty: TrainingDifficulty
  questionMix: QuestionMix
  fallbackFocus: string
  fallbackPersonaName: string
  fallbackPersonaRole: string
  fallbackPersonaStyle: string
}

export interface InterviewScenarioPreset extends LocalizedOption<InterviewScenarioPresetId> {
  focusKey: TranslationKey
  personaNameKey: TranslationKey
  personaRoleKey: TranslationKey
  personaStyleKey: TranslationKey
  framework: ExpressionFramework
  difficulty: TrainingDifficulty
  questionMix: QuestionMix
  fallbackFocus: string
  fallbackPersonaName: string
  fallbackPersonaRole: string
  fallbackPersonaStyle: string
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
  {
    value: 'product_management',
    labelKey: 'training.scenario.productManagement.label',
    descKey: 'training.scenario.productManagement.desc',
    fallbackLabel: 'Product Mgmt',
    fallbackDesc: 'Roadmap, PRD, launches, and stakeholder alignment',
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

export const INTERVIEW_ROLE_PRESETS: InterviewRolePreset[] = [
  {
    value: 'recruiter_screen',
    labelKey: 'training.interviewRole.recruiter.label',
    descKey: 'training.interviewRole.recruiter.desc',
    roleKey: 'training.interviewRole.recruiter.role',
    focusKey: 'training.interviewRole.recruiter.focus',
    fallbackLabel: 'Recruiter',
    fallbackDesc: 'Motivation, fit, salary range, and career story',
    fallbackRole: 'Product Manager Candidate',
    fallbackFocus: 'career story, motivation, role fit, salary expectations',
    level: 'mid',
    questionMix: { behavioral: 55, technical: 20, pressure: 25 },
  },
  {
    value: 'hiring_manager',
    labelKey: 'training.interviewRole.hiringManager.label',
    descKey: 'training.interviewRole.hiringManager.desc',
    roleKey: 'training.interviewRole.hiringManager.role',
    focusKey: 'training.interviewRole.hiringManager.focus',
    fallbackLabel: 'Hiring manager',
    fallbackDesc: 'Product judgment, ownership, impact, and team fit',
    fallbackRole: 'Product Manager Candidate',
    fallbackFocus: 'product judgment, ownership, impact, team fit',
    level: 'senior',
    questionMix: { behavioral: 35, technical: 40, pressure: 25 },
  },
  {
    value: 'product_case_interviewer',
    labelKey: 'training.interviewRole.caseInterviewer.label',
    descKey: 'training.interviewRole.caseInterviewer.desc',
    roleKey: 'training.interviewRole.caseInterviewer.role',
    focusKey: 'training.interviewRole.caseInterviewer.focus',
    fallbackLabel: 'Case interviewer',
    fallbackDesc: 'Product sense, prioritization, metrics, and structure',
    fallbackRole: 'Product Manager Candidate',
    fallbackFocus: 'product sense, prioritization, metrics, problem solving',
    level: 'senior',
    questionMix: { behavioral: 15, technical: 60, pressure: 25 },
  },
  {
    value: 'cross_functional_interviewer',
    labelKey: 'training.interviewRole.crossFunctional.label',
    descKey: 'training.interviewRole.crossFunctional.desc',
    roleKey: 'training.interviewRole.crossFunctional.role',
    focusKey: 'training.interviewRole.crossFunctional.focus',
    fallbackLabel: 'Cross-functional',
    fallbackDesc: 'Engineering, design, data, and business collaboration',
    fallbackRole: 'Product Manager Candidate',
    fallbackFocus: 'collaboration, conflict resolution, technical trade-offs, influence',
    level: 'senior',
    questionMix: { behavioral: 40, technical: 35, pressure: 25 },
  },
  {
    value: 'bar_raiser',
    labelKey: 'training.interviewRole.barRaiser.label',
    descKey: 'training.interviewRole.barRaiser.desc',
    roleKey: 'training.interviewRole.barRaiser.role',
    focusKey: 'training.interviewRole.barRaiser.focus',
    fallbackLabel: 'Bar raiser',
    fallbackDesc: 'Leadership, ambiguity, evidence, and pressure follow-ups',
    fallbackRole: 'Product Manager Candidate',
    fallbackFocus: 'leadership, ambiguity, evidence quality, decision reasoning',
    level: 'senior',
    questionMix: { behavioral: 35, technical: 30, pressure: 35 },
  },
]

export const INTERVIEW_SCENARIO_PRESETS: InterviewScenarioPreset[] = [
  {
    value: 'self_intro_pitch',
    labelKey: 'training.interviewScenario.selfIntro.label',
    descKey: 'training.interviewScenario.selfIntro.desc',
    focusKey: 'training.interviewScenario.selfIntro.focus',
    personaNameKey: 'training.interviewScenario.selfIntro.personaName',
    personaRoleKey: 'training.interviewScenario.selfIntro.personaRole',
    personaStyleKey: 'training.interviewScenario.selfIntro.personaStyle',
    fallbackLabel: 'Self-intro',
    fallbackDesc: 'Open with a crisp PM career story',
    fallbackFocus: '60-90 second self-introduction, motivation, role fit, career transitions',
    fallbackPersonaName: 'Recruiter',
    fallbackPersonaRole: 'Recruiter checking role fit, motivation, and communication clarity',
    fallbackPersonaStyle: 'Friendly but time-boxed, checks motivation and clarity',
    framework: 'pyramid',
    difficulty: 'easy',
    questionMix: { behavioral: 60, technical: 15, pressure: 25 },
  },
  {
    value: 'resume_deep_dive',
    labelKey: 'training.interviewScenario.resumeDeepDive.label',
    descKey: 'training.interviewScenario.resumeDeepDive.desc',
    focusKey: 'training.interviewScenario.resumeDeepDive.focus',
    personaNameKey: 'training.interviewScenario.resumeDeepDive.personaName',
    personaRoleKey: 'training.interviewScenario.resumeDeepDive.personaRole',
    personaStyleKey: 'training.interviewScenario.resumeDeepDive.personaStyle',
    fallbackLabel: 'Resume deep dive',
    fallbackDesc: 'Defend project impact and exact contribution',
    fallbackFocus: 'resume project, product ownership, metrics, trade-offs, retrospective',
    fallbackPersonaName: 'Hiring Manager',
    fallbackPersonaRole: 'Hiring manager probing resume claims and product ownership',
    fallbackPersonaStyle: 'Direct, asks for exact contribution, metrics, and decisions',
    framework: 'star',
    difficulty: 'medium',
    questionMix: { behavioral: 40, technical: 35, pressure: 25 },
  },
  {
    value: 'product_sense_case',
    labelKey: 'training.interviewScenario.productSense.label',
    descKey: 'training.interviewScenario.productSense.desc',
    focusKey: 'training.interviewScenario.productSense.focus',
    personaNameKey: 'training.interviewScenario.productSense.personaName',
    personaRoleKey: 'training.interviewScenario.productSense.personaRole',
    personaStyleKey: 'training.interviewScenario.productSense.personaStyle',
    fallbackLabel: 'Product case',
    fallbackDesc: 'Structure users, problems, solutions, and metrics',
    fallbackFocus: 'product sense, user segmentation, problem framing, prioritization, success metrics',
    fallbackPersonaName: 'Product Case Interviewer',
    fallbackPersonaRole: 'Product case interviewer testing user insight, prioritization, and metrics',
    fallbackPersonaStyle: 'Structured, pushes for user insight, alternatives, and metric trade-offs',
    framework: 'scqa',
    difficulty: 'medium',
    questionMix: { behavioral: 15, technical: 60, pressure: 25 },
  },
  {
    value: 'metrics_growth_case',
    labelKey: 'training.interviewScenario.metricsGrowth.label',
    descKey: 'training.interviewScenario.metricsGrowth.desc',
    focusKey: 'training.interviewScenario.metricsGrowth.focus',
    personaNameKey: 'training.interviewScenario.metricsGrowth.personaName',
    personaRoleKey: 'training.interviewScenario.metricsGrowth.personaRole',
    personaStyleKey: 'training.interviewScenario.metricsGrowth.personaStyle',
    fallbackLabel: 'Metrics case',
    fallbackDesc: 'Diagnose metric movement and propose experiments',
    fallbackFocus: 'metric tree, diagnosis, experiment design, guardrail metrics, trade-offs',
    fallbackPersonaName: 'Growth Interviewer',
    fallbackPersonaRole: 'Growth-oriented product interviewer testing data reasoning',
    fallbackPersonaStyle: 'Analytical, presses assumptions, metric definitions, and experiment quality',
    framework: 'scqa',
    difficulty: 'hard',
    questionMix: { behavioral: 10, technical: 65, pressure: 25 },
  },
  {
    value: 'behavioral_leadership',
    labelKey: 'training.interviewScenario.behavioral.label',
    descKey: 'training.interviewScenario.behavioral.desc',
    focusKey: 'training.interviewScenario.behavioral.focus',
    personaNameKey: 'training.interviewScenario.behavioral.personaName',
    personaRoleKey: 'training.interviewScenario.behavioral.personaRole',
    personaStyleKey: 'training.interviewScenario.behavioral.personaStyle',
    fallbackLabel: 'Behavioral',
    fallbackDesc: 'Answer conflict, failure, influence, ambiguity',
    fallbackFocus: 'conflict, failure, influence without authority, ambiguity, learning',
    fallbackPersonaName: 'Bar Raiser',
    fallbackPersonaRole: 'Bar raiser testing leadership, ownership, and evidence quality',
    fallbackPersonaStyle: 'High-pressure, asks follow-ups until evidence and reflection are specific',
    framework: 'star',
    difficulty: 'hard',
    questionMix: { behavioral: 65, technical: 10, pressure: 25 },
  },
  {
    value: 'cross_functional_round',
    labelKey: 'training.interviewScenario.crossFunctional.label',
    descKey: 'training.interviewScenario.crossFunctional.desc',
    focusKey: 'training.interviewScenario.crossFunctional.focus',
    personaNameKey: 'training.interviewScenario.crossFunctional.personaName',
    personaRoleKey: 'training.interviewScenario.crossFunctional.personaRole',
    personaStyleKey: 'training.interviewScenario.crossFunctional.personaStyle',
    fallbackLabel: 'XFN round',
    fallbackDesc: 'Show collaboration with engineering, design, data, business',
    fallbackFocus: 'technical trade-offs, design conflict, data uncertainty, stakeholder alignment',
    fallbackPersonaName: 'Cross-functional Panel',
    fallbackPersonaRole: 'Engineering and design interviewers testing collaboration patterns',
    fallbackPersonaStyle: 'Cross-functional pressure, challenges trade-offs and alignment methods',
    framework: 'prep',
    difficulty: 'medium',
    questionMix: { behavioral: 45, technical: 30, pressure: 25 },
  },
  {
    value: 'offer_negotiation',
    labelKey: 'training.interviewScenario.offer.label',
    descKey: 'training.interviewScenario.offer.desc',
    focusKey: 'training.interviewScenario.offer.focus',
    personaNameKey: 'training.interviewScenario.offer.personaName',
    personaRoleKey: 'training.interviewScenario.offer.personaRole',
    personaStyleKey: 'training.interviewScenario.offer.personaStyle',
    fallbackLabel: 'Offer negotiation',
    fallbackDesc: 'Discuss comp, level, scope, and timeline',
    fallbackFocus: 'salary expectations, level, scope, competing process, timeline, goodwill',
    fallbackPersonaName: 'Recruiter',
    fallbackPersonaRole: 'Recruiter negotiating compensation, level, and decision timeline',
    fallbackPersonaStyle: 'Negotiation pressure, tests clarity, flexibility, and professionalism',
    framework: 'prep',
    difficulty: 'medium',
    questionMix: { behavioral: 35, technical: 15, pressure: 50 },
  },
]

export const PRODUCT_ROLE_PRESETS: ProductRolePreset[] = [
  {
    value: 'core_pm',
    labelKey: 'training.productRole.core.label',
    descKey: 'training.productRole.core.desc',
    roleKey: 'training.productRole.core.role',
    focusKey: 'training.productRole.core.focus',
    fallbackLabel: 'Core PM',
    fallbackDesc: 'Discovery, roadmap, PRD, and cross-functional alignment',
    fallbackRole: 'Product Manager',
    fallbackFocus: 'B2B SaaS, user research, metrics, roadmap, PRD',
    level: 'mid',
    questionMix: { behavioral: 30, technical: 45, pressure: 25 },
  },
  {
    value: 'growth_pm',
    labelKey: 'training.productRole.growth.label',
    descKey: 'training.productRole.growth.desc',
    roleKey: 'training.productRole.growth.role',
    focusKey: 'training.productRole.growth.focus',
    fallbackLabel: 'Growth PM',
    fallbackDesc: 'Activation, retention, experimentation, and funnel decisions',
    fallbackRole: 'Growth Product Manager',
    fallbackFocus: 'activation, retention, experimentation, funnel analytics',
    level: 'senior',
    questionMix: { behavioral: 25, technical: 50, pressure: 25 },
  },
  {
    value: 'platform_pm',
    labelKey: 'training.productRole.platform.label',
    descKey: 'training.productRole.platform.desc',
    roleKey: 'training.productRole.platform.role',
    focusKey: 'training.productRole.platform.focus',
    fallbackLabel: 'Platform PM',
    fallbackDesc: 'API contracts, reliability, developer experience, and internal scale',
    fallbackRole: 'Platform Product Manager',
    fallbackFocus: 'API platform, developer experience, reliability, internal tools',
    level: 'senior',
    questionMix: { behavioral: 25, technical: 50, pressure: 25 },
  },
  {
    value: 'ai_pm',
    labelKey: 'training.productRole.ai.label',
    descKey: 'training.productRole.ai.desc',
    roleKey: 'training.productRole.ai.role',
    focusKey: 'training.productRole.ai.focus',
    fallbackLabel: 'AI PM',
    fallbackDesc: 'LLM capability, evals, privacy, model cost, and product bets',
    fallbackRole: 'AI Product Manager',
    fallbackFocus: 'LLM features, evaluation, privacy, model cost',
    level: 'senior',
    questionMix: { behavioral: 25, technical: 45, pressure: 30 },
  },
]

export const PRODUCT_SCENARIO_PRESETS: ProductScenarioPreset[] = [
  {
    value: 'roadmap_prioritization',
    labelKey: 'training.productScenario.roadmap.label',
    descKey: 'training.productScenario.roadmap.desc',
    focusKey: 'training.productScenario.roadmap.focus',
    personaNameKey: 'training.productScenario.roadmap.personaName',
    personaRoleKey: 'training.productScenario.roadmap.personaRole',
    personaStyleKey: 'training.productScenario.roadmap.personaStyle',
    fallbackLabel: 'Roadmap priority',
    fallbackDesc: 'Say no, defend sequencing, and keep stakeholders aligned',
    fallbackFocus: 'roadmap prioritization, revenue requests, opportunity sizing, trade-offs',
    fallbackPersonaName: 'Sales Director',
    fallbackPersonaRole: 'Head of Sales pushing for a large enterprise request',
    fallbackPersonaStyle: 'Revenue pressure, asks for dates, challenges prioritization criteria',
    framework: 'pyramid',
    difficulty: 'medium',
    questionMix: { behavioral: 25, technical: 45, pressure: 30 },
  },
  {
    value: 'prd_review',
    labelKey: 'training.productScenario.prd.label',
    descKey: 'training.productScenario.prd.desc',
    focusKey: 'training.productScenario.prd.focus',
    personaNameKey: 'training.productScenario.prd.personaName',
    personaRoleKey: 'training.productScenario.prd.personaRole',
    personaStyleKey: 'training.productScenario.prd.personaStyle',
    fallbackLabel: 'PRD review',
    fallbackDesc: 'Clarify scope, acceptance criteria, and engineering trade-offs',
    fallbackFocus: 'PRD review, scope, acceptance criteria, feasibility, dependencies',
    fallbackPersonaName: 'Engineering Lead',
    fallbackPersonaRole: 'Engineering lead challenging feasibility and edge cases',
    fallbackPersonaStyle: 'Precise, skeptical about ambiguity, presses for concrete acceptance criteria',
    framework: 'scqa',
    difficulty: 'medium',
    questionMix: { behavioral: 20, technical: 55, pressure: 25 },
  },
  {
    value: 'launch_risk_review',
    labelKey: 'training.productScenario.launchRisk.label',
    descKey: 'training.productScenario.launchRisk.desc',
    focusKey: 'training.productScenario.launchRisk.focus',
    personaNameKey: 'training.productScenario.launchRisk.personaName',
    personaRoleKey: 'training.productScenario.launchRisk.personaRole',
    personaStyleKey: 'training.productScenario.launchRisk.personaStyle',
    fallbackLabel: 'Launch risk',
    fallbackDesc: 'Make a go/no-go recommendation under imperfect information',
    fallbackFocus: 'launch readiness, risk mitigation, go/no-go decision, owner alignment',
    fallbackPersonaName: 'Executive Sponsor',
    fallbackPersonaRole: 'Executive sponsor asking whether to launch this week',
    fallbackPersonaStyle: 'High pressure, asks for a clear recommendation, risk owner, and mitigation',
    framework: 'prep',
    difficulty: 'hard',
    questionMix: { behavioral: 20, technical: 45, pressure: 35 },
  },
  {
    value: 'user_feedback_triage',
    labelKey: 'training.productScenario.feedback.label',
    descKey: 'training.productScenario.feedback.desc',
    focusKey: 'training.productScenario.feedback.focus',
    personaNameKey: 'training.productScenario.feedback.personaName',
    personaRoleKey: 'training.productScenario.feedback.personaRole',
    personaStyleKey: 'training.productScenario.feedback.personaStyle',
    fallbackLabel: 'Feedback triage',
    fallbackDesc: 'Separate signal from anecdotes and turn feedback into action',
    fallbackFocus: 'user feedback, severity, frequency, segmentation, follow-up plan',
    fallbackPersonaName: 'Customer Success Lead',
    fallbackPersonaRole: 'Customer success lead escalating urgent user complaints',
    fallbackPersonaStyle: 'User-advocate pressure, brings anecdotes, asks for immediate action',
    framework: 'scqa',
    difficulty: 'medium',
    questionMix: { behavioral: 30, technical: 45, pressure: 25 },
  },
  {
    value: 'executive_update',
    labelKey: 'training.productScenario.executive.label',
    descKey: 'training.productScenario.executive.desc',
    focusKey: 'training.productScenario.executive.focus',
    personaNameKey: 'training.productScenario.executive.personaName',
    personaRoleKey: 'training.productScenario.executive.personaRole',
    personaStyleKey: 'training.productScenario.executive.personaStyle',
    fallbackLabel: 'Executive update',
    fallbackDesc: 'Communicate progress, risk, asks, and decision options clearly',
    fallbackFocus: 'executive update, progress, risk, options, decision ask',
    fallbackPersonaName: 'CEO',
    fallbackPersonaRole: 'CEO asking for impact, risk, and why the plan changed',
    fallbackPersonaStyle: 'Impatient, asks for business impact, decision options, and confidence level',
    framework: 'pyramid',
    difficulty: 'hard',
    questionMix: { behavioral: 20, technical: 40, pressure: 40 },
  },
  {
    value: 'stakeholder_conflict',
    labelKey: 'training.productScenario.conflict.label',
    descKey: 'training.productScenario.conflict.desc',
    focusKey: 'training.productScenario.conflict.focus',
    personaNameKey: 'training.productScenario.conflict.personaName',
    personaRoleKey: 'training.productScenario.conflict.personaRole',
    personaStyleKey: 'training.productScenario.conflict.personaStyle',
    fallbackLabel: 'Stakeholder conflict',
    fallbackDesc: 'Align design, engineering, and business when incentives diverge',
    fallbackFocus: 'stakeholder conflict, shared goal, constraints, decision facilitation',
    fallbackPersonaName: 'Stakeholder Panel',
    fallbackPersonaRole: 'Cross-functional stakeholder panel with conflicting priorities',
    fallbackPersonaStyle: 'Mixed incentives, interrupts with conflicting asks, tests facilitation skill',
    framework: 'scqa',
    difficulty: 'hard',
    questionMix: { behavioral: 35, technical: 35, pressure: 30 },
  },
]

export const DEFAULT_TRAINING_STUDIO_CONFIG: TrainingStudioConfig = {
  scenario: 'interview',
  interviewRolePreset: 'hiring_manager',
  interviewScenarioPreset: 'resume_deep_dive',
  productRolePreset: '',
  productScenarioPreset: '',
  difficulty: 'medium',
  framework: 'star',
  role: 'Product Manager',
  level: 'senior',
  techStack: 'PM interview, resume projects, product sense, metrics, stakeholder alignment',
  questionMix: {
    behavioral: 40,
    technical: 35,
    pressure: 25,
  },
  questionCount: 8,
  replyLanguage: DEFAULT_TRAINING_REPLY_LANGUAGE,
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

function cleanCapabilityText(value: unknown): string | null {
  if (value === undefined || value === null) return null
  const text = redactCapabilitySecretText(String(value).trim())
  return text || null
}

function uniqueCapabilityTexts(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.map(cleanCapabilityText).filter((value): value is string => Boolean(value))))
}

function redactCapabilitySecretText(value: string): string {
  return value
    .replace(/sk-[A-Za-z0-9_-]{6,}/g, 'sk-***')
    .replace(/\b(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}/gi, '$1 ***')
    .replace(/\b(api[_-]?key|authorization|password|secret|token)(\s*[:=]\s*)([^,\s;]+)/gi, '$1$2***')
}

function normalizeCapabilityToken(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function hasModelCapability(choice: TrainingStudioModelCapabilityInput, tokens: string[]): boolean {
  const wanted = new Set(tokens)
  return (choice.capabilities ?? []).some((capability) => {
    const normalized = normalizeCapabilityToken(capability)
    return wanted.has(normalized) || tokens.some((token) => normalized.includes(token))
  })
}

function readinessPriority(status: TrainingStudioReadinessStatus): number {
  if (status === 'blocked') return 3
  if (status === 'warning') return 2
  if (status === 'unknown') return 1
  return 0
}

function combineReadinessStatus(items: TrainingStudioCapabilityItem[]): TrainingStudioReadinessStatus {
  if (items.length === 0) return 'unknown'
  return items.reduce<TrainingStudioReadinessStatus>((current, item) => (
    readinessPriority(item.status) > readinessPriority(current) ? item.status : current
  ), 'ready')
}

function countRealtimeBlockingIssues(capabilities: RealtimeCapabilities | null | undefined): number {
  if (!capabilities) return 0
  return [
    ...(capabilities.pipecat.readiness?.blockingReasons ?? []),
    ...(capabilities.pipecat.errors ?? []),
  ].length
}

function normalizeTrainingStudioReadinessStatus(value: unknown): TrainingStudioReadinessStatus {
  const status = String(value ?? '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (status === 'ready' || status === 'warning' || status === 'blocked' || status === 'unknown') {
    return status
  }
  if (status === 'available') return 'ready'
  if (status === 'unavailable' || status === 'missingdependency' || status === 'missing_dependency') {
    return 'blocked'
  }
  return 'unknown'
}

export function getPipecatReadinessStatus(
  capabilities: RealtimeCapabilities['pipecat'] | null | undefined,
): TrainingStudioReadinessStatus {
  if (!capabilities) return 'unknown'

  const backendStatus = normalizeTrainingStudioReadinessStatus(capabilities.readiness?.status)
  if (backendStatus !== 'unknown') return backendStatus
  if (capabilities.readyForCall) return 'ready'
  if (
    capabilities.available
    || capabilities.coreAvailable
    || capabilities.websocketAvailable
    || capabilities.vadAvailable
    || capabilities.sttAvailable
    || capabilities.ttsAvailable
    || capabilities.llmAvailable
    || capabilities.turnDetectionAvailable
  ) {
    return 'warning'
  }
  return 'blocked'
}

function normalizeRuntimeCapabilityKind(value: unknown): RuntimeCapabilityKind {
  return String(value ?? '').trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function normalizeRuntimeCapabilityStatus(value: unknown): RuntimeCapabilityStatus {
  return String(value ?? 'unknown').trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function normalizeRuntimeCapabilityItems(
  registry: RuntimeCapabilityRegistry | null | undefined,
): RuntimeCapabilityRegistryItem[] {
  if (!registry || typeof registry !== 'object') return []
  if (Array.isArray(registry.capabilities)) return registry.capabilities
  const byKind = registry.by_kind ?? registry.byKind
  if (!byKind || typeof byKind !== 'object') return []
  return Object.values(byKind).flatMap((items) => Array.isArray(items) ? items : [])
}

function runtimeCapabilityIsEnabled(item: RuntimeCapabilityRegistryItem): boolean {
  return item.enabled !== false
}

function runtimeCapabilityIsReady(item: RuntimeCapabilityRegistryItem): boolean {
  const status = normalizeRuntimeCapabilityStatus(item.readiness?.status ?? item.status)
  if (item.ready === true) return true
  if (item.readiness?.ready === true) return true
  return runtimeCapabilityIsEnabled(item) && ['ready', 'available'].includes(status)
}

function runtimeCapabilityIsBlocked(item: RuntimeCapabilityRegistryItem): boolean {
  const status = normalizeRuntimeCapabilityStatus(item.readiness?.status ?? item.status)
  return ['blocked', 'missingdependency', 'missing_dependency', 'unavailable'].includes(status)
}

function runtimeCapabilityIsDisabled(item: RuntimeCapabilityRegistryItem): boolean {
  const status = normalizeRuntimeCapabilityStatus(item.status)
  return item.enabled === false || status === 'disabled'
}

function getRuntimeCapabilityIssues(item: RuntimeCapabilityRegistryItem): RealtimeReadinessIssue[] {
  return [
    ...(item.readiness?.blockingReasons ?? []),
    ...(item.readiness?.warnings ?? []),
    ...(item.readiness?.errors ?? []),
    ...(item.blockingReasons ?? []),
    ...(item.errors ?? []),
  ]
}

function getRuntimeCapabilityIssueText(issue: RealtimeReadinessIssue): string | null {
  return cleanCapabilityText(issue.message)
    ?? cleanCapabilityText(issue.code)
    ?? cleanCapabilityText(issue.feature)
}

function realtimeFeatureBooleans(capabilities: RealtimeCapabilities | null | undefined): boolean[] {
  if (!capabilities) return []
  return [
    capabilities.pipecat.coreAvailable,
    capabilities.pipecat.websocketAvailable,
    capabilities.pipecat.vadAvailable,
    capabilities.pipecat.sttAvailable,
    capabilities.pipecat.ttsAvailable,
    capabilities.pipecat.llmAvailable,
    capabilities.pipecat.turnDetectionAvailable,
  ]
}

function buildProviderModelReadiness(
  modelChoices: TrainingStudioModelCapabilityInput[],
): TrainingStudioCapabilityItem {
  const providers = uniqueCapabilityTexts(modelChoices.map((choice) => choice.providerLabel || choice.provider))
  const selectableModels = modelChoices.filter((choice) => !choice.disabled)
  const defaultChoice = selectableModels.find((choice) => choice.isDefault) ?? selectableModels[0] ?? null
  const status: TrainingStudioReadinessStatus = selectableModels.length > 0
    ? 'ready'
    : modelChoices.length > 0
      ? 'warning'
      : 'unknown'
  const defaultLabel = defaultChoice
    ? [defaultChoice.providerLabel || defaultChoice.provider, defaultChoice.modelLabel || defaultChoice.model]
      .map(cleanCapabilityText)
      .filter(Boolean)
      .join(' / ')
    : ''

  return {
    key: 'provider-model',
    label: 'Provider / model registry',
    status,
    detail: defaultLabel
      ? `Default route: ${defaultLabel}. Provider-neutral model metadata is available to the training runtime.`
      : 'No selectable provider/model route is available yet.',
    tags: [
      `${providers.length} provider${providers.length === 1 ? '' : 's'}`,
      `${selectableModels.length} selectable model${selectableModels.length === 1 ? '' : 's'}`,
      ...uniqueCapabilityTexts(selectableModels.flatMap((choice) => choice.capabilities ?? [])).slice(0, 4),
    ],
    metrics: [
      { label: 'providers', value: String(providers.length) },
      { label: 'models', value: String(modelChoices.length) },
      { label: 'selectable', value: String(selectableModels.length) },
    ],
  }
}

function buildRealtimeReadinessItem(
  capabilities: RealtimeCapabilities | null | undefined,
  readyFeatureCount: number,
  totalFeatureCount: number,
  blockingIssues: number,
): TrainingStudioCapabilityItem {
  if (!capabilities) {
    return {
      key: 'realtime-runtime',
      label: 'Realtime runtime',
      status: 'unknown',
      detail: 'Realtime capabilities have not been loaded from the backend yet.',
      tags: ['Pipecat'],
      metrics: [
        { label: 'pipecat', value: 'not loaded' },
        { label: 'blockers', value: 'unknown' },
      ],
    }
  }

  const status = getPipecatReadinessStatus(capabilities.pipecat)
  const pipecatReady = status === 'ready'
  const statusLabel = pipecatReady
    ? 'can start calls'
    : status === 'warning'
      ? 'is not fully ready'
      : 'is blocked'

  return {
    key: 'realtime-runtime',
    label: 'Realtime runtime',
    status,
    detail: `Pipecat ${statusLabel} with ${readyFeatureCount}/${totalFeatureCount} pipeline features available.`,
    tags: [
      pipecatReady
        ? 'Pipecat call-ready'
        : status === 'warning'
          ? 'Pipecat needs attention'
          : 'Pipecat blocked',
    ],
    metrics: [
      { label: 'pipecat features', value: `${readyFeatureCount}/${totalFeatureCount}` },
      { label: 'blockers', value: String(blockingIssues) },
      { label: 'missing modules', value: String(capabilities.pipecat.missingModules.length) },
    ],
  }
}

function buildAgentMcpReadiness(
  modelChoices: TrainingStudioModelCapabilityInput[],
  toolCapableModels: number,
  mcpCapableModels: number,
  capabilityRegistry: RuntimeCapabilityRegistry | null | undefined,
): TrainingStudioCapabilityItem {
  const selectableModels = modelChoices.filter((choice) => !choice.disabled)
  const runtimeItems = normalizeRuntimeCapabilityItems(capabilityRegistry)
  const agentItems = runtimeItems.filter((item) => normalizeRuntimeCapabilityKind(item.kind) === 'agent')
  const toolItems = runtimeItems.filter((item) => normalizeRuntimeCapabilityKind(item.kind) === 'tool')
  const mcpItems = runtimeItems.filter((item) => normalizeRuntimeCapabilityKind(item.kind) === 'mcp_server')
  const relevantItems = [...agentItems, ...toolItems, ...mcpItems]
  const enabledItems = relevantItems.filter(runtimeCapabilityIsEnabled)
  const readyItems = relevantItems.filter(runtimeCapabilityIsReady)
  const blockedItems = relevantItems.filter(runtimeCapabilityIsBlocked)
  const disabledItems = relevantItems.filter(runtimeCapabilityIsDisabled)
  const explicitIssues = relevantItems.flatMap(getRuntimeCapabilityIssues)
  const issueText = uniqueCapabilityTexts(explicitIssues.map(getRuntimeCapabilityIssueText))
  const status: TrainingStudioReadinessStatus = relevantItems.length > 0
    ? readyItems.length > 0
      ? (blockedItems.length > 0 || disabledItems.length > 0 ? 'warning' : 'ready')
      : blockedItems.length > 0 || disabledItems.length > 0
        ? 'blocked'
        : 'warning'
    : mcpCapableModels > 0
      ? 'ready'
      : toolCapableModels > 0
        ? 'warning'
        : modelChoices.length > 0
          ? 'blocked'
          : 'unknown'

  return {
    key: 'agent-mcp',
    label: 'Agent / MCP capability',
    status,
    detail: relevantItems.length > 0
      ? mcpItems.length > 0
        ? 'Backend agent and MCP inventory is visible through a secret-free capability registry.'
        : toolItems.length > 0
          ? 'Tool capability is visible, but MCP server inventory is still incomplete.'
          : 'Agent capability metadata is visible, but tool and MCP inventory is still incomplete.'
      : mcpCapableModels > 0
        ? 'MCP-capable model metadata is visible; agent/tool events can be surfaced without changing training semantics.'
        : toolCapableModels > 0
          ? 'Tool-capable model metadata is visible. MCP server inventory still needs an explicit backend readiness payload.'
          : 'No tool-capable model metadata is visible for agent or MCP workflows.',
    tags: [
      'agent_tool_use events',
      'agent_message events',
      relevantItems.length > 0
        ? `${enabledItems.length} enabled inventory items`
        : toolCapableModels > 0 ? 'tool-capable models' : 'no tool models',
      relevantItems.length > 0
        ? `${readyItems.length} ready inventory items`
        : mcpCapableModels > 0 ? 'MCP tagged' : 'MCP inventory pending',
      ...issueText.slice(0, 2),
    ],
    metrics: [
      { label: 'tool models', value: String(toolCapableModels) },
      { label: 'MCP models', value: String(mcpCapableModels) },
      { label: 'inventory', value: String(relevantItems.length) },
      { label: 'blocked', value: String(blockedItems.length) },
      { label: 'selectable', value: String(selectableModels.length) },
    ],
  }
}

export function buildTrainingStudioCapabilityReadiness(
  input: BuildTrainingStudioCapabilityReadinessInput = {},
): TrainingStudioCapabilityReadiness {
  const modelChoices = input.modelChoices ?? []
  const realtimeCapabilities = input.realtimeCapabilities ?? null
  const capabilityRegistry = input.capabilityRegistry ?? null
  const providers = uniqueCapabilityTexts(modelChoices.map((choice) => choice.provider))
  const selectableModels = modelChoices.filter((choice) => !choice.disabled)
  const toolCapableModels = modelChoices.filter((choice) => (
    !choice.disabled
    && hasModelCapability(choice, ['tools', 'tool', 'tool_calling', 'function_calling', 'function', 'agent'])
  )).length
  const mcpCapableModels = modelChoices.filter((choice) => (
    !choice.disabled
    && hasModelCapability(choice, ['mcp', 'mcp_tools', 'mcp_server'])
  )).length
  const featureBooleans = realtimeFeatureBooleans(realtimeCapabilities)
  const pipecatReadyFeatures = featureBooleans.filter(Boolean).length
  const realtimeBlockingIssues = countRealtimeBlockingIssues(realtimeCapabilities)
  const providerModel = buildProviderModelReadiness(modelChoices)
  const realtime = buildRealtimeReadinessItem(
    realtimeCapabilities,
    pipecatReadyFeatures,
    featureBooleans.length || 7,
    realtimeBlockingIssues,
  )
  const agentMcp = buildAgentMcpReadiness(
    modelChoices,
    toolCapableModels,
    mcpCapableModels,
    capabilityRegistry,
  )
  const foundation: TrainingStudioCapabilityItem[] = [
    {
      key: 'text-runtime',
      label: 'LibreChat-style text runtime',
      status: 'ready',
      detail: 'Conversation tree, branch selection, edit, retry, fork, and selected-path replay are represented at the training boundary.',
      tags: ['message tree', 'branch-aware replay', 'review metadata'],
      metrics: [
        { label: 'write actions', value: 'edit/retry/fork' },
        { label: 'review source', value: 'session/report/progress' },
      ],
    },
    {
      key: 'training-semantics',
      label: 'TalkWise training semantics',
      status: 'ready',
      detail: 'Training goal, persona, scenario, dispatcher, evaluation, report, and live guidance metadata stay separate from provider/model selection.',
      tags: ['training session', 'rubric', 'growth report'],
      metrics: [
        { label: 'metadata lanes', value: 'separated' },
        { label: 'review path', value: 'branch-aware' },
      ],
    },
    realtime,
    providerModel,
  ]

  return {
    overallStatus: combineReadinessStatus([...foundation, agentMcp]),
    foundation,
    providerModel,
    realtime,
    agentMcp,
    modelCounts: {
      providers: providers.length,
      models: modelChoices.length,
      selectableModels: selectableModels.length,
      toolCapableModels,
      mcpCapableModels,
    },
    realtimeCounts: {
      pipecatFeatures: featureBooleans.length || 7,
      pipecatReadyFeatures,
      blockingIssues: realtimeBlockingIssues,
    },
  }
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

export function getInterviewRolePreset(value: InterviewRolePresetId | ''): InterviewRolePreset | undefined {
  return INTERVIEW_ROLE_PRESETS.find((item) => item.value === value)
}

export function getInterviewScenarioPreset(
  value: InterviewScenarioPresetId | '',
): InterviewScenarioPreset | undefined {
  return INTERVIEW_SCENARIO_PRESETS.find((item) => item.value === value)
}

export function getProductRolePreset(value: ProductRolePresetId | ''): ProductRolePreset | undefined {
  return PRODUCT_ROLE_PRESETS.find((item) => item.value === value)
}

export function getProductScenarioPreset(
  value: ProductScenarioPresetId | '',
): ProductScenarioPreset | undefined {
  return PRODUCT_SCENARIO_PRESETS.find((item) => item.value === value)
}

export function getProductScenarioPresetLabel(value: ProductScenarioPresetId | '', t?: Translate): string {
  const option = getProductScenarioPreset(value)
  return option ? translate(t, option.labelKey, option.fallbackLabel) : ''
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

export function toTrainingRuntimeDifficulty(difficulty: TrainingDifficulty): 'easy' | 'normal' | 'hard' {
  return difficulty === 'medium' ? 'normal' : difficulty
}

export function toBattleDifficulty(difficulty: TrainingDifficulty): 'easy' | 'normal' | 'hard' {
  return toTrainingRuntimeDifficulty(difficulty)
}

export function buildTrainingStudioPrompt(config: TrainingStudioConfig, description: string, t?: Translate): string {
  const mix = normalizeQuestionMix(config.questionMix)
  const scenario = getTrainingScenarioLabel(config.scenario, t)
  const difficulty = getTrainingDifficultyLabel(config.difficulty, t)
  const framework = getExpressionFrameworkLabel(config.framework, t)
  const level = getTrainingLevelLabel(config.level, t)
  const productScenario =
    config.scenario === 'product_management'
      ? getProductScenarioPreset(config.productScenarioPreset)
      : undefined
  const interviewScenario =
    config.scenario === 'interview'
      ? getInterviewScenarioPreset(config.interviewScenarioPreset)
      : undefined
  const notSpecified = translate(t, 'training.prompt.notSpecified', 'Not specified')
  const interviewScenarioLines = interviewScenario
    ? [
        `- ${translate(t, 'training.prompt.interviewRound', 'Interview round')}: ${translate(t, interviewScenario.labelKey, interviewScenario.fallbackLabel)}`,
        `- ${translate(t, 'training.prompt.interviewer', 'Interviewer')}: ${translate(t, interviewScenario.personaRoleKey, interviewScenario.fallbackPersonaRole)}`,
        `- ${translate(t, 'training.prompt.interviewFocus', 'Interview focus')}: ${translate(t, interviewScenario.focusKey, interviewScenario.fallbackFocus)}`,
      ]
    : []
  const productScenarioLines = productScenario
    ? [
        `- ${translate(t, 'training.prompt.productScenario', 'Product drill')}: ${translate(t, productScenario.labelKey, productScenario.fallbackLabel)}`,
        `- ${translate(t, 'training.prompt.counterpart', 'Counterpart')}: ${translate(t, productScenario.personaRoleKey, productScenario.fallbackPersonaRole)}`,
        `- ${translate(t, 'training.prompt.pmFocus', 'PM focus')}: ${translate(t, productScenario.focusKey, productScenario.fallbackFocus)}`,
      ]
    : []

  return [
    description.trim(),
    '',
    translate(t, 'training.prompt.heading', 'Training Studio configuration:'),
    `- ${translate(t, 'training.prompt.scenario', 'Scenario')}: ${scenario}`,
    `- ${translate(t, 'training.prompt.difficulty', 'Difficulty')}: ${difficulty}`,
    `- ${translate(t, 'training.prompt.framework', 'Expression framework')}: ${framework}`,
    `- ${translate(t, 'training.prompt.role', 'Target role')}: ${config.role || notSpecified}`,
    `- ${translate(t, 'training.prompt.level', 'Level')}: ${level || notSpecified}`,
    `- ${translate(t, 'training.prompt.techStack', 'Domain / tools')}: ${config.techStack || notSpecified}`,
    `- ${translate(t, 'training.prompt.replyLanguage', 'AI reply language')}: ${formatTrainingReplyLanguagePromptValue(config.replyLanguage)}`,
    ...interviewScenarioLines,
    ...productScenarioLines,
    `- ${translate(t, 'training.prompt.questionMix', 'Question mix')}: ${translate(t, 'training.launcher.behavioral', 'behavioral')} ${mix.behavioral}%, ${translate(t, 'training.launcher.technical', 'technical')} ${mix.technical}%, ${translate(t, 'training.launcher.pressure', 'pressure')} ${mix.pressure}%`,
    `- ${translate(t, 'training.prompt.questionCount', 'Question count')}: ${config.questionCount}`,
    translate(t, 'training.prompt.replyLanguageRule', 'The AI counterpart must reply in the selected language unless the learner explicitly asks to switch.'),
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

function hasObjectShape(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function unwrapApiResponse<T>(value: ApiResponse<T> | T): T {
  if (hasObjectShape(value) && 'data' in value) {
    return value.data as T
  }
  return value as T
}

function trainingStudioErrorText(value: unknown): string | null {
  if (typeof value === 'string') {
    const text = value.trim()
    return text || null
  }
  if (!hasObjectShape(value)) return null
  return (
    trainingStudioErrorText(value.message)
    || trainingStudioErrorText(value.detail)
    || trainingStudioErrorText(value.details)
  )
}

async function readTrainingStudioError(resp: Response, fallback: string): Promise<Error> {
  const json = await resp.json().catch(() => null)
  const message = (
    trainingStudioErrorText(hasObjectShape(json) ? json.error : null)
    || trainingStudioErrorText(hasObjectShape(json) ? json.detail : null)
    || trainingStudioErrorText(hasObjectShape(json) ? json.message : null)
  )
  return new Error(message || `${fallback}: ${resp.status}`)
}

export async function fetchRealtimeCapabilities(): Promise<RealtimeCapabilities> {
  const resp = await fetch(REALTIME_CAPABILITIES_API, {
    headers: getAuthRequestHeaders(),
  })
  if (!resp.ok) {
    throw await readTrainingStudioError(resp, 'Failed to fetch realtime capabilities')
  }
  return unwrapApiResponse<RealtimeCapabilities>(await resp.json())
}

export function buildVideoAnswerUploadUrl({
  trainingSessionId,
  roomId,
}: VideoAnswerUploadRequest): string {
  const params = new URLSearchParams({
    training_session_id: trainingSessionId,
    room_id: String(roomId),
  })
  return `${TRAINING_STUDIO_API_BASE}/video-answers?${params.toString()}`
}

export async function uploadVideoAnswer(
  blob: Blob,
  request: VideoAnswerUploadRequest,
): Promise<VideoAnswerUploadResult> {
  const filename = request.filename || `video-answer-${Date.now()}${extensionForVideoMimeType(blob.type)}`
  const resp = await fetch(buildVideoAnswerUploadUrl(request), {
    method: 'POST',
    headers: {
      ...getAuthRequestHeaders(),
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
