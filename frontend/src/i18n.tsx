/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type Locale = 'zh' | 'en'
export type TranslationParams = Record<string, string | number>
export type Translate = (key: TranslationKey, params?: TranslationParams) => string
export type TranslateInline = (zhText: string, enText: string, params?: TranslationParams) => string

const DEFAULT_LOCALE: Locale = 'zh'
const STORAGE_KEY = 'talk-training-studio.locale'

const en = {
  'language.zh': '中文',
  'language.en': 'English',
  'app.searchPlaceholder': 'Search or type a command...',
  'app.languageLabel': 'Language',
  'app.levelTitle': 'Lv.5 Communication Expert',
  'app.avatarInitial': 'G',
  'nav.home': 'Home',
  'nav.trainingStudio': 'Training Studio',
  'nav.trainingStudioShort': 'Train',
  'nav.chat': 'Chat',
  'nav.battlePrep': 'Battle Prep',
  'nav.growth': 'Growth',
  'nav.settings': 'Settings',
  'nav.me': 'Me',
  'command.rooms': 'Rooms',
  'command.actions': 'Actions',
  'command.personas': 'Personas',
  'command.empty': 'No matching results',
  'command.footer.select': 'Select',
  'command.footer.open': 'Open',
  'command.footer.close': 'Close',
  'command.action.battlePrep': 'Battle Prep',
  'command.action.newChat': 'New Chat',
  'command.action.growth': 'Growth Report',
  'command.roomType.battlePrep': 'Battle prep',
  'command.roomType.group': 'Group',
  'command.roomType.private': 'Private',
  'training.page.title': 'Communication Training Studio',
  'training.page.subtitle': 'Pick the scenario, response mode, and pressure profile before entering a live practice room.',
  'training.page.startRoom': 'Start Room',
  'training.page.responseModeAria': 'Response mode',
  'training.mode.text.label': 'Text',
  'training.mode.text.desc': 'Structured written practice with rubrics and replay.',
  'training.mode.text.instruction': 'Session mode: text. Run a focused written communication drill with structured feedback.',
  'training.mode.voice.label': 'Voice',
  'training.mode.voice.desc': 'Start in chat with voice controls ready for spoken answers.',
  'training.mode.voice.instruction': 'Session mode: voice. Ask concise questions, wait for spoken answers, and give short turn-by-turn feedback.',
  'training.mode.video.label': 'Video',
  'training.mode.video.desc': 'Record camera answers and keep the replay attached to messages.',
  'training.mode.video.instruction': 'Session mode: video. Ask answer prompts that work well as recorded video responses and review delivery, structure, and evidence.',
  'training.goal.label': 'Practice Goal',
  'training.goal.placeholder': 'Example: Practice answering senior frontend system-design interview questions with stronger evidence and tighter structure.',
  'training.side.aria': 'Session actions',
  'training.launch.title': 'Launch Path',
  'training.launch.openChat': 'Open Chat Room',
  'training.launch.openBattlePrep': 'Open Battle Prep Flow',
  'training.modeEntry.title': 'Mode Entry',
  'training.modeEntry.voice': 'After entering the room, use the microphone button in the chat input to answer by voice.',
  'training.modeEntry.video': 'After entering the room, use the video button in the chat input to record and send answers.',
  'training.modeEntry.text': 'After entering the room, type answers in the chat input and request analysis or coaching.',
  'training.error.startFailed': 'Failed to start session',
  'training.launcher.aria': 'Training Studio configuration',
  'training.launcher.title': 'Communication Training Studio',
  'training.launcher.subtitle': 'Choose the scenario, pressure, structure, and question mix before generating a practice opponent.',
  'training.launcher.reset': 'Reset',
  'training.launcher.scenario': 'Scenario',
  'training.launcher.difficulty': 'Difficulty',
  'training.launcher.framework': 'Expression Framework',
  'training.launcher.role': 'Role',
  'training.launcher.level': 'Level',
  'training.launcher.techStack': 'Tech Stack',
  'training.launcher.questions': 'Questions',
  'training.launcher.questionOption': '{count} questions',
  'training.launcher.questionMix': 'Question Mix',
  'training.launcher.total': 'Total {total}%',
  'training.launcher.behavioral': 'Behavioral',
  'training.launcher.technical': 'Technical',
  'training.launcher.pressure': 'Pressure',
  'training.placeholder.role': 'Example: Frontend Engineer',
  'training.placeholder.techStack': 'Example: React, TypeScript, Node.js',
  'training.defaults.role': 'Frontend Engineer',
  'training.defaults.roleFallback': 'Communication',
  'training.defaults.techStack': 'React, TypeScript',
  'training.scenario.interview.label': 'Interview',
  'training.scenario.interview.desc': 'Interview answers and follow-ups',
  'training.scenario.sales.label': 'Sales',
  'training.scenario.sales.desc': 'Objections, value, and next steps',
  'training.scenario.negotiation.label': 'Negotiation',
  'training.scenario.negotiation.desc': 'Trade-offs, leverage, and concessions',
  'training.scenario.workplace.label': 'Workplace',
  'training.scenario.workplace.desc': 'Alignment, feedback, and reporting',
  'training.difficulty.easy.label': 'Easy',
  'training.difficulty.easy.desc': 'Gentle prompts',
  'training.difficulty.medium.label': 'Medium',
  'training.difficulty.medium.desc': 'Normal pressure',
  'training.difficulty.hard.label': 'Hard',
  'training.difficulty.hard.desc': 'Tough follow-ups',
  'training.framework.prep.label': 'PREP',
  'training.framework.prep.desc': 'Point, reason, example, point',
  'training.framework.star.label': 'STAR',
  'training.framework.star.desc': 'Situation, task, action, result',
  'training.framework.scqa.label': 'SCQA',
  'training.framework.scqa.desc': 'Situation, complication, question, answer',
  'training.framework.pyramid.label': 'Pyramid',
  'training.framework.pyramid.desc': 'Answer first, then layered support',
  'training.level.intern.label': 'Intern',
  'training.level.junior.label': 'Junior',
  'training.level.mid.label': 'Mid-level',
  'training.level.senior.label': 'Senior',
  'training.level.staff.label': 'Staff',
  'training.level.manager.label': 'Manager',
  'training.prompt.defaultGoal': '{role} {scenario} practice',
  'training.prompt.personaName': '{role} Coach',
  'training.prompt.personaRole': '{level} {scenario} trainer',
  'training.prompt.personaStyle': '{difficulty} pressure, {framework} feedback, {mode} response mode',
  'training.prompt.structurePoint': '{framework} structure',
  'training.prompt.deliveryPoint': '{mode} delivery',
  'training.prompt.evidencePoint': 'evidence-backed answers',
  'training.prompt.heading': 'Training Studio configuration:',
  'training.prompt.scenario': 'Scenario',
  'training.prompt.difficulty': 'Difficulty',
  'training.prompt.framework': 'Expression framework',
  'training.prompt.role': 'Target role',
  'training.prompt.level': 'Level',
  'training.prompt.techStack': 'Tech stack',
  'training.prompt.questionMix': 'Question mix',
  'training.prompt.questionCount': 'Question count',
  'training.prompt.notSpecified': 'Not specified',
} as const

export type TranslationKey = keyof typeof en

const zh = {
  'language.zh': '中文',
  'language.en': 'English',
  'app.searchPlaceholder': '搜索或输入命令...',
  'app.languageLabel': '语言',
  'app.levelTitle': 'Lv.5 沟通达人',
  'app.avatarInitial': '顾',
  'nav.home': '首页',
  'nav.trainingStudio': '训练工作台',
  'nav.trainingStudioShort': '训练',
  'nav.chat': '对话',
  'nav.battlePrep': '紧急备战',
  'nav.growth': '成长',
  'nav.settings': '设置',
  'nav.me': '我的',
  'command.rooms': '对话',
  'command.actions': '操作',
  'command.personas': '角色',
  'command.empty': '没有找到匹配结果',
  'command.footer.select': '选择',
  'command.footer.open': '打开',
  'command.footer.close': '关闭',
  'command.action.battlePrep': '紧急备战',
  'command.action.newChat': '新建对话',
  'command.action.growth': '成长报告',
  'command.roomType.battlePrep': '备战',
  'command.roomType.group': '群组',
  'command.roomType.private': '私聊',
  'training.page.title': '沟通训练工作台',
  'training.page.subtitle': '先选择场景、作答方式和压力强度，再进入实时练习房间。',
  'training.page.startRoom': '开始练习',
  'training.page.responseModeAria': '作答方式',
  'training.mode.text.label': '文字',
  'training.mode.text.desc': '用结构化文字练习回答，并保留复盘记录。',
  'training.mode.text.instruction': '训练模式：文字。请进行聚焦的书面沟通演练，并给出结构化反馈。',
  'training.mode.voice.label': '语音',
  'training.mode.voice.desc': '进入对话后可直接使用语音控件作答。',
  'training.mode.voice.instruction': '训练模式：语音。请提出简洁问题，等待语音回答，并给出简短的逐轮反馈。',
  'training.mode.video.label': '视频',
  'training.mode.video.desc': '录制自拍视频回答，并把回放保留在消息中。',
  'training.mode.video.instruction': '训练模式：视频。请提出适合视频回答的问题，并评估表达状态、结构和证据。',
  'training.goal.label': '练习目标',
  'training.goal.placeholder': '例如：练习高级前端系统设计面试回答，让证据更扎实、结构更紧凑。',
  'training.side.aria': '训练操作',
  'training.launch.title': '启动方式',
  'training.launch.openChat': '打开对话房间',
  'training.launch.openBattlePrep': '进入备战流程',
  'training.modeEntry.title': '进入方式',
  'training.modeEntry.voice': '进入房间后，使用输入区的麦克风按钮进行语音回答。',
  'training.modeEntry.video': '进入房间后，使用输入区的视频按钮录制并发送回答。',
  'training.modeEntry.text': '进入房间后，在输入区键入回答，并按需请求分析或教练反馈。',
  'training.error.startFailed': '启动训练失败',
  'training.launcher.aria': '训练工作台配置',
  'training.launcher.title': '沟通训练工作台',
  'training.launcher.subtitle': '选择场景、压力、表达框架和题目配比，用来生成练习对手。',
  'training.launcher.reset': '重置',
  'training.launcher.scenario': '场景',
  'training.launcher.difficulty': '难度',
  'training.launcher.framework': '表达框架',
  'training.launcher.role': '角色',
  'training.launcher.level': '级别',
  'training.launcher.techStack': '技术栈',
  'training.launcher.questions': '题目数',
  'training.launcher.questionOption': '{count} 道题',
  'training.launcher.questionMix': '题目配比',
  'training.launcher.total': '总计 {total}%',
  'training.launcher.behavioral': '行为题',
  'training.launcher.technical': '技术题',
  'training.launcher.pressure': '压力题',
  'training.placeholder.role': '例如：前端工程师',
  'training.placeholder.techStack': '例如：React、TypeScript、Node.js',
  'training.defaults.role': '前端工程师',
  'training.defaults.roleFallback': '沟通',
  'training.defaults.techStack': 'React、TypeScript',
  'training.scenario.interview.label': '面试',
  'training.scenario.interview.desc': '面试回答与追问练习',
  'training.scenario.sales.label': '销售',
  'training.scenario.sales.desc': '异议处理、价值表达和推进下一步',
  'training.scenario.negotiation.label': '谈判',
  'training.scenario.negotiation.desc': '取舍、筹码和让步策略',
  'training.scenario.workplace.label': '职场',
  'training.scenario.workplace.desc': '对齐目标、反馈沟通和汇报表达',
  'training.difficulty.easy.label': '轻松',
  'training.difficulty.easy.desc': '温和提示',
  'training.difficulty.medium.label': '标准',
  'training.difficulty.medium.desc': '正常压力',
  'training.difficulty.hard.label': '高压',
  'training.difficulty.hard.desc': '强追问压力',
  'training.framework.prep.label': 'PREP',
  'training.framework.prep.desc': '观点、理由、例子、重申观点',
  'training.framework.star.label': 'STAR',
  'training.framework.star.desc': '情境、任务、行动、结果',
  'training.framework.scqa.label': 'SCQA',
  'training.framework.scqa.desc': '情境、冲突、问题、答案',
  'training.framework.pyramid.label': '金字塔',
  'training.framework.pyramid.desc': '先给答案，再分层支撑',
  'training.level.intern.label': '实习',
  'training.level.junior.label': '初级',
  'training.level.mid.label': '中级',
  'training.level.senior.label': '高级',
  'training.level.staff.label': '专家',
  'training.level.manager.label': '管理者',
  'training.prompt.defaultGoal': '{role}{scenario}练习',
  'training.prompt.personaName': '{role}教练',
  'training.prompt.personaRole': '{level}{scenario}训练师',
  'training.prompt.personaStyle': '{difficulty}压力，{framework}反馈，{mode}作答模式',
  'training.prompt.structurePoint': '{framework}结构',
  'training.prompt.deliveryPoint': '{mode}表达',
  'training.prompt.evidencePoint': '有证据支撑的回答',
  'training.prompt.heading': '训练工作台配置：',
  'training.prompt.scenario': '场景',
  'training.prompt.difficulty': '难度',
  'training.prompt.framework': '表达框架',
  'training.prompt.role': '目标角色',
  'training.prompt.level': '级别',
  'training.prompt.techStack': '技术栈',
  'training.prompt.questionMix': '题目配比',
  'training.prompt.questionCount': '题目数',
  'training.prompt.notSpecified': '未填写',
} satisfies Record<TranslationKey, string>

export const SUPPORTED_LOCALES: { value: Locale; labelKey: TranslationKey }[] = [
  { value: 'zh', labelKey: 'language.zh' },
  { value: 'en', labelKey: 'language.en' },
]

const messages: Record<Locale, Record<TranslationKey, string>> = {
  en,
  zh,
}

interface I18nContextValue {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: Translate
  tr: TranslateInline
}

const I18nContext = createContext<I18nContextValue | null>(null)

function normalizeLocale(value: string | null | undefined): Locale | null {
  if (!value) return null
  const tag = value.toLowerCase()
  if (tag.startsWith('zh') || tag === 'cn') return 'zh'
  if (tag.startsWith('en')) return 'en'
  return null
}

function getInitialLocale(): Locale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE

  try {
    const stored = normalizeLocale(window.localStorage.getItem(STORAGE_KEY))
    if (stored) return stored
  } catch {
    return DEFAULT_LOCALE
  }

  return DEFAULT_LOCALE
}

function formatMessage(template: string, params?: TranslationParams): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(params[key] ?? `{${key}}`))
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale)

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale)
    try {
      window.localStorage.setItem(STORAGE_KEY, nextLocale)
    } catch {
      // Persistence is a convenience; the in-memory language still updates.
    }
  }, [])

  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
  }, [locale])

  const t = useCallback<Translate>(
    (key, params) => formatMessage(messages[locale][key] ?? messages.en[key] ?? key, params),
    [locale],
  )

  const tr = useCallback<TranslateInline>(
    (zhText, enText, params) => formatMessage(locale === 'zh' ? zhText : enText, params),
    [locale],
  )

  const value = useMemo(() => ({ locale, setLocale, t, tr }), [locale, setLocale, t, tr])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext)
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider')
  }
  return context
}
