import type { Translate, TranslationKey, TranslationParams } from '../i18n'

export type TrainingScenario = 'interview' | 'sales' | 'negotiation' | 'workplace' | 'product_management'
export type TrainingDifficulty = 'easy' | 'medium' | 'hard'
export type ExpressionFramework = 'prep' | 'star' | 'scqa' | 'pyramid'
export type TrainingLevel = 'intern' | 'junior' | 'mid' | 'senior' | 'staff' | 'manager'
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

export function toBattleDifficulty(difficulty: TrainingDifficulty): 'easy' | 'normal' | 'hard' {
  return difficulty === 'medium' ? 'normal' : difficulty
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
    ...interviewScenarioLines,
    ...productScenarioLines,
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
