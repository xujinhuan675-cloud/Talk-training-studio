import type { Translate, TranslationKey } from '../i18n'

export const GROWTH_DIMENSIONS = [
  'persuasion',
  'emotional_management',
  'active_listening',
  'structured_expression',
  'conflict_resolution',
  'stakeholder_alignment',
] as const

export type GrowthDimensionKey = (typeof GROWTH_DIMENSIONS)[number]

const GROWTH_DIMENSION_SET = new Set<string>(GROWTH_DIMENSIONS)

export type GrowthSkillField = 'name' | 'desc' | 'unlock' | 'suggestion'

export function isGrowthDimensionKey(value: string | undefined): value is GrowthDimensionKey {
  return Boolean(value && GROWTH_DIMENSION_SET.has(value))
}

export function growthDimensionLabelKey(dim: GrowthDimensionKey): TranslationKey {
  return `growth.dimension.${dim}.label` as TranslationKey
}

export function growthSkillKey(dim: GrowthDimensionKey, field: GrowthSkillField): TranslationKey {
  return `growth.skill.${dim}.${field}` as TranslationKey
}

export function getGrowthDimensionLabel(dim: string | undefined, t: Translate): string {
  return isGrowthDimensionKey(dim) ? t(growthDimensionLabelKey(dim)) : dim || ''
}
