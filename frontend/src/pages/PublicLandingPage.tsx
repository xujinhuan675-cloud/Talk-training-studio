import { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  BarChart3,
  ClipboardCheck,
  Headphones,
  MessageSquareText,
  Mic,
  ShieldCheck,
  Sparkles,
  Target,
  UsersRound,
} from 'lucide-react'
import PublicProductLayout from '../components/layout/PublicProductLayout'
import { useAuthContext } from '../contexts/AuthContext'
import { useI18n } from '../i18n'
import './PublicLandingPage.css'

type PreviewTabId = 'scenario' | 'dialogue' | 'review'

interface PreviewTab {
  id: PreviewTabId
  label: string
  heading: string
  detail: string
  status: string
  icon: typeof Target
}

// Adapted from outside-project/new-api-main/web/src/features/home/ (Hero -> Stats -> Features -> HowItWorks -> CTA).
// The structure and responsive interactions are retained; gateway content, metrics, routes, and branding are TalkWise-specific.
export default function PublicLandingPage() {
  return (
    <PublicProductLayout>
      <main className="public-landing">
        <Hero />
        <Stats />
        <Features />
        <HowItWorks />
        <CTA />
      </main>
    </PublicProductLayout>
  )
}

function Hero() {
  const { tr } = useI18n()
  const { requestSignIn } = useAuthContext()

  return (
    <section className="public-landing-hero" aria-labelledby="public-landing-title">
      <div className="public-landing-container public-landing-hero-grid">
        <div className="public-landing-hero-copy">
          <p className="public-landing-eyebrow"><Sparkles size={15} />{tr('AI 沟通训练', 'AI communication training')}</p>
          <h1 id="public-landing-title">TalkWise</h1>
          <p className="public-landing-hero-lead">
            {tr('把重要沟通放进可重复演练的真实场景，在对话中获得提示，并在结束后回看每一次选择。', 'Rehearse important conversations in realistic scenarios, receive guidance in the moment, and review every decision afterwards.')}
          </p>
          <div className="public-landing-actions">
            <button
              className="public-landing-button public-landing-button--primary"
              type="button"
              onClick={requestSignIn}
            >
              {tr('开始训练', 'Start training')}<ArrowRight size={16} />
            </button>
            <a className="public-landing-button public-landing-button--secondary" href="#workflow">
              {tr('查看训练流程', 'See the workflow')}
            </a>
          </div>
          <div className="public-landing-hero-topics" aria-label={tr('训练主题', 'Training topics')}>
            <span>{tr('面试', 'Interviews')}</span>
            <span>{tr('销售', 'Sales')}</span>
            <span>{tr('谈判', 'Negotiation')}</span>
            <span>{tr('职场沟通', 'Workplace')}</span>
          </div>
        </div>
        <TrainingWorkspacePreview />
      </div>
    </section>
  )
}

function TrainingWorkspacePreview() {
  const { tr } = useI18n()
  const tabs = useMemo<PreviewTab[]>(() => [
    {
      id: 'scenario',
      label: tr('场景', 'Scenario'),
      heading: tr('准备一次关键对话', 'Prepare for a key conversation'),
      detail: tr('选择目标、对手角色与练习难度。', 'Choose the goal, counterpart, and level of challenge.'),
      status: tr('场景已就绪', 'Scenario ready'),
      icon: Target,
    },
    {
      id: 'dialogue',
      label: tr('对话', 'Dialogue'),
      heading: tr('在角色中完成表达', 'Practice in role'),
      detail: tr('文本或语音对话保持在同一训练上下文。', 'Text and voice practice stay in one training context.'),
      status: tr('对话进行中', 'Dialogue in progress'),
      icon: MessageSquareText,
    },
    {
      id: 'review',
      label: tr('复盘', 'Review'),
      heading: tr('带着下一步继续练', 'Continue with the next step'),
      detail: tr('回看表现、建议与需要再次练习的重点。', 'Review performance, guidance, and what to rehearse next.'),
      status: tr('复盘可用', 'Review available'),
      icon: ClipboardCheck,
    },
  ], [tr])
  const [activeTabId, setActiveTabId] = useState<PreviewTabId>('scenario')
  const activeIndex = tabs.findIndex((tab) => tab.id === activeTabId)
  const activeTab = tabs[activeIndex] ?? tabs[0]

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mediaQuery.matches) return undefined
    const interval = window.setInterval(() => {
      setActiveTabId((current) => tabs[(tabs.findIndex((tab) => tab.id === current) + 1) % tabs.length].id)
    }, 4600)
    return () => window.clearInterval(interval)
  }, [tabs])

  const Icon = activeTab.icon

  return (
    <div className="public-landing-preview" aria-label={tr('TalkWise 训练工作台预览', 'TalkWise training workspace preview')}>
      <div className="public-landing-preview-bar">
        <div className="public-landing-preview-tabs" role="tablist" aria-label={tr('训练环节', 'Training stages')}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={tab.id === activeTab.id}
              className={tab.id === activeTab.id ? 'is-active' : ''}
              onClick={() => setActiveTabId(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <span className="public-landing-preview-live"><i />{tr('训练中', 'Training')}</span>
      </div>
      <div className="public-landing-preview-body">
        <div className="public-landing-preview-stage">
          <div className="public-landing-preview-icon"><Icon size={22} /></div>
          <span className="public-landing-preview-status">{activeTab.status}</span>
          <h2>{activeTab.heading}</h2>
          <p>{activeTab.detail}</p>
        </div>
        <div className="public-landing-preview-side" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>
      <div className="public-landing-preview-footer">
        <img src="/talkwise-icon.svg" alt="" aria-hidden="true" />
        <span>{tr('训练闭环', 'Training loop')}</span>
        <span className="public-landing-preview-footer-step">{activeIndex + 1} / {tabs.length}</span>
      </div>
    </div>
  )
}

function Stats() {
  const { tr } = useI18n()
  const items = [
    [Target, tr('场景化演练', 'Scenario practice')],
    [Mic, tr('文本与语音', 'Text and voice')],
    [Headphones, tr('实时提示', 'Live guidance')],
    [BarChart3, tr('复盘与成长', 'Review and growth')],
  ] as const

  return (
    <section className="public-landing-stats" aria-label={tr('核心能力', 'Core capabilities')}>
      <div className="public-landing-container public-landing-stats-grid">
        {items.map(([Icon, label]) => <div key={label}><Icon size={20} /><span>{label}</span></div>)}
      </div>
    </section>
  )
}

function Features() {
  const { tr } = useI18n()
  const features = [
    { icon: Target, title: tr('从目标开始', 'Start with a goal'), description: tr('围绕面试、销售、谈判与职场情境建立练习。', 'Build practice around interviews, sales, negotiation, and workplace situations.') },
    { icon: UsersRound, title: tr('明确对手角色', 'Define the counterpart'), description: tr('用 persona、利益相关者和难度控制对话的压力与方向。', 'Use personas, stakeholders, and difficulty to shape pressure and direction.') },
    { icon: MessageSquareText, title: tr('保持训练上下文', 'Keep training context'), description: tr('训练对话、提示和会话状态在同一条路径里连续呈现。', 'Dialogue, guidance, and session state stay on one continuous path.') },
    { icon: ShieldCheck, title: tr('可追溯的复盘', 'Traceable review'), description: tr('区分训练会话、报告与成长记录，回到需要强化的地方。', 'Keep session, report, and growth records distinct, then return to what needs work.') },
  ]
  const additional = [
    [Mic, tr('语音练习', 'Voice practice')],
    [ClipboardCheck, tr('结构化反馈', 'Structured feedback')],
    [BarChart3, tr('成长记录', 'Growth records')],
    [Headphones, tr('实时引导', 'Live coaching')],
  ] as const

  return (
    <section className="public-landing-features" id="capabilities" aria-labelledby="public-landing-features-title">
      <div className="public-landing-container">
        <div className="public-landing-section-heading">
          <p>{tr('核心能力', 'Core capabilities')}</p>
          <h2 id="public-landing-features-title">{tr('把沟通练习变成可持续改进的工作流', 'Turn communication practice into a repeatable improvement workflow')}</h2>
        </div>
        <div className="public-landing-feature-grid">
          {features.map(({ icon: Icon, title, description }) => (
            <article key={title} className="public-landing-feature">
              <Icon size={21} />
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
        <div className="public-landing-feature-row">
          {additional.map(([Icon, label]) => <div key={label}><Icon size={20} /><span>{label}</span></div>)}
        </div>
      </div>
    </section>
  )
}

function HowItWorks() {
  const { tr } = useI18n()
  const steps = [
    { icon: Target, title: tr('设定目标', 'Set the goal'), description: tr('选择要练的场景与对手角色。', 'Choose the scenario and counterpart to rehearse.') },
    { icon: MessageSquareText, title: tr('完成对话', 'Practice the conversation'), description: tr('在文本或语音中完成一轮真实表达。', 'Complete a realistic exchange in text or voice.') },
    { icon: ClipboardCheck, title: tr('复盘下一步', 'Review the next step'), description: tr('回看表现，并针对弱点继续训练。', 'Review performance and keep working on weak points.') },
  ]

  return (
    <section className="public-landing-how" id="workflow" aria-labelledby="public-landing-how-title">
      <div className="public-landing-container">
        <div className="public-landing-section-heading public-landing-section-heading--center">
          <p>{tr('训练流程', 'Training flow')}</p>
          <h2 id="public-landing-how-title">{tr('三个环节，回到下一次更好的表达', 'Three stages that lead to the next better conversation')}</h2>
        </div>
        <div className="public-landing-steps">
          {steps.map(({ icon: Icon, title, description }, index) => (
            <article key={title} className="public-landing-step">
              <div className="public-landing-step-icon"><Icon size={24} /><span>{index + 1}</span></div>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

function CTA() {
  const { tr } = useI18n()
  const { requestSignIn } = useAuthContext()
  return (
    <section className="public-landing-cta" aria-labelledby="public-landing-cta-title">
      <div className="public-landing-container public-landing-cta-inner">
        <h2 id="public-landing-cta-title">{tr('从下一场重要沟通开始准备', 'Prepare for the next conversation that matters')}</h2>
        <p>{tr('登录后进入训练工作台，选择你的场景并开始演练。', 'Sign in to open the training workspace, choose a scenario, and begin.')}</p>
        <button
          className="public-landing-button public-landing-button--primary"
          type="button"
          onClick={requestSignIn}
        >
          {tr('进入训练', 'Enter training')}<ArrowRight size={16} />
        </button>
      </div>
    </section>
  )
}
