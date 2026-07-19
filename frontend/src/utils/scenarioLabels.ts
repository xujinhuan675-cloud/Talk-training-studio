import type { TranslateInline } from '../i18n'
import type {
  ScenarioTrainingCategory,
  ScenarioTrainingDifficulty,
  ScenarioTrainingStatus,
} from '../data/trainingScenarios'

export type LocalizedText = readonly [zh: string, en: string]
export type ScenarioDifficultyFilter = 'all' | ScenarioTrainingDifficulty
export type ScenarioCategoryFilter = 'all' | ScenarioTrainingCategory
export type ScenarioStatusFilter = 'all' | ScenarioTrainingStatus

export const scenarioDifficultyOptions: ScenarioTrainingDifficulty[] = ['easy', 'medium', 'hard', 'expert']
export const scenarioCategoryOptions: ScenarioTrainingCategory[] = ['sales', 'customer_service', 'negotiation', 'interview', 'workplace']
export const scenarioStatusOptions: ScenarioTrainingStatus[] = ['not_started', 'in_progress', 'completed', 'failed']

export function translateLabel(label: LocalizedText, tr: TranslateInline): string {
  return tr(label[0], label[1])
}

export function getScenarioDifficultyLabel(value: ScenarioTrainingDifficulty, tr: TranslateInline): string {
  if (value === 'easy') return tr('轻量', 'Light')
  if (value === 'medium') return tr('标准', 'Standard')
  if (value === 'hard') return tr('高压', 'High pressure')
  return tr('专家', 'Expert')
}

export function getScenarioDifficultyFilterLabel(value: ScenarioDifficultyFilter, tr: TranslateInline): string {
  return value === 'all' ? tr('全部难度', 'All difficulties') : getScenarioDifficultyLabel(value, tr)
}

export function getScenarioCategoryLabel(value: ScenarioTrainingCategory, tr: TranslateInline): string {
  if (value === 'sales') return tr('销售', 'Sales')
  if (value === 'customer_service') return tr('客服', 'Customer service')
  if (value === 'negotiation') return tr('谈判', 'Negotiation')
  if (value === 'interview') return tr('面试', 'Interview')
  return tr('职场沟通', 'Workplace')
}

export function getScenarioCategoryFilterLabel(value: ScenarioCategoryFilter, tr: TranslateInline): string {
  return value === 'all' ? tr('全部类型', 'All categories') : getScenarioCategoryLabel(value, tr)
}

export function getScenarioStatusLabel(status: ScenarioTrainingStatus, tr: TranslateInline): string {
  if (status === 'not_started') return tr('未开始', 'Not started')
  if (status === 'in_progress') return tr('练习中', 'In progress')
  if (status === 'completed') return tr('已完成', 'Completed')
  return tr('失败', 'Failed')
}

export function getScenarioStatusFilterLabel(value: ScenarioStatusFilter, tr: TranslateInline): string {
  return value === 'all' ? tr('全部状态', 'All statuses') : getScenarioStatusLabel(value, tr)
}
