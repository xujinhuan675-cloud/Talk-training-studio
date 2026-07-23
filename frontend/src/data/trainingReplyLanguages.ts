import { LIVE_COACH_LANGUAGE_OPTIONS } from './liveCoachLanguages'

export const DEFAULT_TRAINING_REPLY_LANGUAGE = 'zh-CN'

const REPLY_LANGUAGE_PROMPT_LABELS: Record<string, string> = {
  'zh-CN': 'Chinese (Simplified)',
  'zh-TW': 'Chinese (Traditional)',
  'en-US': 'English',
  ja: 'Japanese',
  ko: 'Korean',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
}

export function normalizeTrainingReplyLanguage(value: string | null | undefined): string {
  const text = value?.trim()
  return text || DEFAULT_TRAINING_REPLY_LANGUAGE
}

export function getTrainingReplyLanguagePromptLabel(value: string | null | undefined): string {
  const code = normalizeTrainingReplyLanguage(value)
  return REPLY_LANGUAGE_PROMPT_LABELS[code]
    ?? LIVE_COACH_LANGUAGE_OPTIONS.find((option) => option.code === code)?.label
    ?? code
}

export function formatTrainingReplyLanguagePromptValue(value: string | null | undefined): string {
  const code = normalizeTrainingReplyLanguage(value)
  const label = getTrainingReplyLanguagePromptLabel(code)
  return label && label !== code ? `${label} (${code})` : code
}

export function buildTrainingReplyLanguageMetadata(
  value: string | null | undefined,
  source: string,
): Record<string, unknown> {
  const replyLanguage = normalizeTrainingReplyLanguage(value)
  return {
    replyLanguage,
    reply_language: replyLanguage,
    language: {
      replyLanguage,
      reply_language: replyLanguage,
      source,
    },
  }
}
