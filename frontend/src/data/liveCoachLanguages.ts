export interface LiveCoachLanguageOption {
  code: string
  label: string
}

type LiveCoachLocale = 'zh' | 'en' | string

const zhLanguageLabels: Record<string, string> = {
  'en-US': '英语（美国）',
  'zh-CN': '简体中文',
  'zh-TW': '繁体中文',
}

export const LIVE_COACH_LANGUAGE_OPTIONS: readonly LiveCoachLanguageOption[] = [
  { code: 'af', label: 'Afrikaans' },
  { code: 'am', label: 'Amharic' },
  { code: 'ar', label: 'Arabic' },
  { code: 'az', label: 'Azerbaijani' },
  { code: 'bg', label: 'Bulgarian' },
  { code: 'bn', label: 'Bengali' },
  { code: 'bs', label: 'Bosnian' },
  { code: 'ca', label: 'Catalan' },
  { code: 'cs', label: 'Czech' },
  { code: 'cy', label: 'Welsh' },
  { code: 'da', label: 'Danish' },
  { code: 'de', label: 'German' },
  { code: 'el', label: 'Greek' },
  { code: 'en-US', label: 'English' },
  { code: 'es', label: 'Spanish' },
  { code: 'et', label: 'Estonian' },
  { code: 'eu', label: 'Basque' },
  { code: 'fa', label: 'Persian' },
  { code: 'fi', label: 'Finnish' },
  { code: 'fil', label: 'Filipino' },
  { code: 'fr', label: 'French' },
  { code: 'ga', label: 'Irish' },
  { code: 'gl', label: 'Galician' },
  { code: 'gu', label: 'Gujarati' },
  { code: 'he', label: 'Hebrew' },
  { code: 'hi', label: 'Hindi' },
  { code: 'hr', label: 'Croatian' },
  { code: 'hu', label: 'Hungarian' },
  { code: 'hy', label: 'Armenian' },
  { code: 'id', label: 'Indonesian' },
  { code: 'is', label: 'Icelandic' },
  { code: 'it', label: 'Italian' },
  { code: 'ja', label: 'Japanese' },
  { code: 'jv', label: 'Javanese' },
  { code: 'ka', label: 'Georgian' },
  { code: 'kk', label: 'Kazakh' },
  { code: 'km', label: 'Khmer' },
  { code: 'kn', label: 'Kannada' },
  { code: 'ko', label: 'Korean' },
  { code: 'lo', label: 'Lao' },
  { code: 'lt', label: 'Lithuanian' },
  { code: 'lv', label: 'Latvian' },
  { code: 'mk', label: 'Macedonian' },
  { code: 'ml', label: 'Malayalam' },
  { code: 'mn', label: 'Mongolian' },
  { code: 'mr', label: 'Marathi' },
  { code: 'ms', label: 'Malay' },
  { code: 'my', label: 'Burmese' },
  { code: 'ne', label: 'Nepali' },
  { code: 'nl', label: 'Dutch' },
  { code: 'no', label: 'Norwegian' },
  { code: 'pa', label: 'Punjabi' },
  { code: 'pl', label: 'Polish' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'ro', label: 'Romanian' },
  { code: 'ru', label: 'Russian' },
  { code: 'si', label: 'Sinhala' },
  { code: 'sk', label: 'Slovak' },
  { code: 'sl', label: 'Slovenian' },
  { code: 'sq', label: 'Albanian' },
  { code: 'sr', label: 'Serbian' },
  { code: 'sv', label: 'Swedish' },
  { code: 'sw', label: 'Swahili' },
  { code: 'ta', label: 'Tamil' },
  { code: 'te', label: 'Telugu' },
  { code: 'th', label: 'Thai' },
  { code: 'tr', label: 'Turkish' },
  { code: 'uk', label: 'Ukrainian' },
  { code: 'ur', label: 'Urdu' },
  { code: 'uz', label: 'Uzbek' },
  { code: 'vi', label: 'Vietnamese' },
  { code: 'zh-CN', label: 'Chinese (Simplified)' },
  { code: 'zh-TW', label: 'Chinese (Traditional)' },
  { code: 'zu', label: 'Zulu' },
] as const

export function getLiveCoachLanguageLabel(
  code: string | null | undefined,
  locale: LiveCoachLocale = 'en',
): string {
  if (!code) return ''
  if (locale === 'zh' && zhLanguageLabels[code]) return zhLanguageLabels[code]
  const fallback = LIVE_COACH_LANGUAGE_OPTIONS.find((option) => option.code === code)?.label ?? code
  if (locale !== 'zh') return fallback

  try {
    const [language, region] = code.split('-')
    const languageName = new Intl.DisplayNames(['zh-CN'], { type: 'language' }).of(language)
    if (!languageName) return fallback
    if (!region) return languageName
    const regionName = new Intl.DisplayNames(['zh-CN'], { type: 'region' }).of(region)
    return regionName ? `${languageName}（${regionName}）` : languageName
  } catch {
    return fallback
  }
}
