import React, { useState, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import html2canvas from 'html2canvas'
import {
  Loader2,
  Sparkles,
  Check,
  Lock,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  Minus,
  Download,
  Share2,
  Flame,
  Star,
  Zap,
  Trophy,
} from 'lucide-react'
import { useGrowth, type SkillPathNode, type DimensionKey } from '../hooks/useGrowth'
import { generateProfileCard, type ProfileCard as ProfileCardData } from '../services/api'
import ProfileCard from '../components/ProfileCard'
import { useI18n, type TranslateInline } from '../i18n'
import { PageShell } from '../components/ui/page'
import './GrowthPage.css'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DIMENSION_LABELS_ZH: Record<string, string> = {
  persuasion: '说服力',
  emotional_management: '情绪管理',
  active_listening: '倾听回应',
  structured_expression: '结构化表达',
  conflict_resolution: '冲突处理',
  stakeholder_alignment: '利益对齐',
}

const DIMENSION_LABELS_EN: Record<string, string> = {
  persuasion: 'Persuasion',
  emotional_management: 'Emotion Management',
  active_listening: 'Active Listening',
  structured_expression: 'Structured Expression',
  conflict_resolution: 'Conflict Resolution',
  stakeholder_alignment: 'Stakeholder Alignment',
}

const DIMENSIONS = Object.keys(DIMENSION_LABELS_ZH)

/** Map dimension keys to the 6 skill names from the task spec */
const SKILL_NAMES: Record<DimensionKey, string> = {
  persuasion: '入门对话',
  emotional_management: '情绪管理',
  active_listening: '向上管理',
  structured_expression: '高层博弈',
  conflict_resolution: '冲突处理',
  stakeholder_alignment: '共识达成',
}

const SKILL_NAMES_EN: Record<DimensionKey, string> = {
  persuasion: 'Opening Dialogue',
  emotional_management: 'Emotion Management',
  active_listening: 'Managing Up',
  structured_expression: 'Executive Framing',
  conflict_resolution: 'Conflict Resolution',
  stakeholder_alignment: 'Consensus Building',
}

const SKILL_DESCRIPTIONS: Record<DimensionKey, string> = {
  persuasion: '掌握基础沟通技巧，能够清晰表达观点并说服他人',
  emotional_management: '在高压场景中保持冷静，有效管理自身与对方情绪',
  active_listening: '与上级建立信任关系，高效汇报并争取资源支持',
  structured_expression: '在复杂利益格局中找到突破口，达成战略目标',
  conflict_resolution: '在分歧中寻找共识，化解冲突并维护关系',
  stakeholder_alignment: '协调多方利益诉求，推动达成共识性决策',
}

const SKILL_DESCRIPTIONS_EN: Record<DimensionKey, string> = {
  persuasion: 'Master basic communication skills and clearly express persuasive points.',
  emotional_management: 'Stay calm under pressure and manage both your own and the other side’s emotions.',
  active_listening: 'Build trust with leaders, report efficiently, and win resource support.',
  structured_expression: 'Find leverage in complex stakeholder situations and move toward strategic goals.',
  conflict_resolution: 'Find common ground in disagreement, resolve conflict, and protect the relationship.',
  stakeholder_alignment: 'Coordinate multiple interests and drive consensus-based decisions.',
}

const SKILL_UNLOCK_CONDITIONS: Record<DimensionKey, string> = {
  persuasion: '完成 3 次对话评估且平均分 >= 3.0',
  emotional_management: '完成 3 次情绪管理评估且平均分 >= 3.0',
  active_listening: '完成 3 次倾听回应评估且平均分 >= 3.0',
  structured_expression: '完成 3 次结构化表达评估且平均分 >= 3.0',
  conflict_resolution: '完成 3 次冲突处理评估且平均分 >= 3.0',
  stakeholder_alignment: '完成 3 次利益对齐评估且平均分 >= 3.0',
}

const SKILL_UNLOCK_CONDITIONS_EN: Record<DimensionKey, string> = {
  persuasion: 'Complete 3 dialogue evaluations with an average score >= 3.0',
  emotional_management: 'Complete 3 emotion management evaluations with an average score >= 3.0',
  active_listening: 'Complete 3 active listening evaluations with an average score >= 3.0',
  structured_expression: 'Complete 3 structured expression evaluations with an average score >= 3.0',
  conflict_resolution: 'Complete 3 conflict resolution evaluations with an average score >= 3.0',
  stakeholder_alignment: 'Complete 3 stakeholder alignment evaluations with an average score >= 3.0',
}

const SKILL_SUGGESTIONS: Record<DimensionKey, string> = {
  persuasion: '尝试一场需要说服对方的模拟对话',
  emotional_management: '练习一场情绪波动较大的冲突场景',
  active_listening: '在下一场对话中专注展示向上汇报能力',
  structured_expression: '用金字塔原理结构化你的下一次发言',
  conflict_resolution: '模拟一场需要调解各方分歧的会议',
  stakeholder_alignment: '练习寻找多方利益交集的沟通策略',
}

const SKILL_SUGGESTIONS_EN: Record<DimensionKey, string> = {
  persuasion: 'Try a simulation where you need to persuade the other side.',
  emotional_management: 'Practice a conflict scenario with high emotional volatility.',
  active_listening: 'Focus on upward reporting in your next conversation.',
  structured_expression: 'Use the pyramid principle to structure your next response.',
  conflict_resolution: 'Simulate a meeting where you must mediate disagreements.',
  stakeholder_alignment: 'Practice finding overlap across multiple stakeholder interests.',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface RadarDataPoint {
  dimension: string
  latest: number
  average: number
}

function buildRadarData(
  evaluations: { scores: Record<string, { score: number }> }[],
  tr: TranslateInline,
): RadarDataPoint[] {
  return DIMENSIONS.map((dim) => {
    const latest = evaluations.length > 0 ? (evaluations[0].scores[dim]?.score ?? 0) : 0
    const allScores = evaluations.map((ev) => ev.scores[dim]?.score ?? 0).filter((s) => s > 0)
    const average =
      allScores.length > 0
        ? Math.round((allScores.reduce((a, b) => a + b, 0) / allScores.length) * 10) / 10
        : 0
    return { dimension: tr(DIMENSION_LABELS_ZH[dim], DIMENSION_LABELS_EN[dim]), latest, average }
  })
}

function getDimensionLabel(dim: string, tr: TranslateInline): string {
  return tr(DIMENSION_LABELS_ZH[dim] || dim, DIMENSION_LABELS_EN[dim] || dim)
}

function scoreToGrade(score: number): string {
  if (score >= 4.7) return 'A+'
  if (score >= 4.3) return 'A'
  if (score >= 4.0) return 'A-'
  if (score >= 3.7) return 'B+'
  if (score >= 3.3) return 'B'
  if (score >= 3.0) return 'B-'
  if (score >= 2.7) return 'C+'
  if (score >= 2.3) return 'C'
  if (score >= 2.0) return 'C-'
  return 'D'
}

function gradeClass(score: number): string {
  if (score >= 3.5) return 'high'
  if (score >= 2.5) return 'mid'
  return 'low'
}

/** Compute week-over-week change per dimension. Compares latest vs second-latest eval. */
function computeDimensionChanges(
  evaluations: { scores: Record<string, { score: number }> }[],
): Record<string, number> {
  const changes: Record<string, number> = {}
  if (evaluations.length < 2) return changes
  for (const dim of DIMENSIONS) {
    const latest = evaluations[0].scores[dim]?.score ?? 0
    const previous = evaluations[1].scores[dim]?.score ?? 0
    changes[dim] = Math.round((latest - previous) * 10) / 10
  }
  return changes
}

/** Determine skill status from SkillPathNode data */
function getSkillStatus(
  node: SkillPathNode,
  index: number,
  allNodes: SkillPathNode[],
): 'completed' | 'current' | 'locked' {
  if (node.unlocked) return 'completed'
  // The first non-unlocked node after unlocked ones is "current"
  const allBefore = allNodes.slice(0, index)
  const anyUnlockedBefore = allBefore.length === 0 || allBefore.some((n) => n.unlocked)
  if (anyUnlockedBefore && !node.unlocked) {
    // Check if this is the first locked one
    const firstLockedIdx = allNodes.findIndex((n) => !n.unlocked)
    if (firstLockedIdx === index) return 'current'
  }
  return 'locked'
}

/** Build a short feedback summary from the evaluation's dimension scores */
function buildFeedbackSummary(
  scores: Record<string, { score: number; suggestion?: string }>,
  tr: TranslateInline,
): string {
  const entries = Object.entries(scores)
  // Find best and worst
  let best = entries[0]
  let worst = entries[0]
  for (const entry of entries) {
    if (entry[1].score > best[1].score) best = entry
    if (entry[1].score < worst[1].score) worst = entry
  }
  const bestLabel = getDimensionLabel(best?.[0], tr)
  const worstLabel = getDimensionLabel(worst?.[0], tr)
  if (best && worst && best[0] !== worst[0]) {
    return tr(
      '{bestLabel} 表现最佳 ({bestScore})，{worstLabel} 有提升空间 ({worstScore})',
      '{bestLabel} is strongest ({bestScore}); {worstLabel} has room to improve ({worstScore})',
      {
        bestLabel,
        bestScore: best[1].score,
        worstLabel,
        worstScore: worst[1].score,
      },
    )
  }
  return worst?.[1]?.suggestion || ''
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const GrowthPage: React.FC = () => {
  const navigate = useNavigate()
  const { tr, locale } = useI18n()
  const {
    dashboard,
    loading,
    error,
    xp,
    levelInfo,
    streak,
    skillPath,
  } = useGrowth()

  const [profileCard, setProfileCard] = useState<ProfileCardData | null>(null)
  const [profileCardLoading, setProfileCardLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)

  const handleGenerateCard = async () => {
    setProfileCardLoading(true)
    try {
      const card = await generateProfileCard()
      setProfileCard(card)
    } catch (e) {
      console.error(e)
    } finally {
      setProfileCardLoading(false)
    }
  }

  const handleDownload = async () => {
    const el = cardRef.current
    if (!el) return
    setDownloading(true)
    try {
      const canvas = await html2canvas(el, { scale: 2, backgroundColor: '#fff' })
      const link = document.createElement('a')
      link.download = tr('沟通力名片.png', 'communication-profile-card.png')
      link.href = canvas.toDataURL('image/png')
      link.click()
    } finally {
      setDownloading(false)
    }
  }

  // Loading state
  if (loading) {
    return (
      <PageShell width="wide" className="growth-page">
        <div className="gp-loading">
          <Loader2 size={24} className="gp-spin" />
          <span>{tr('加载成长数据...', 'Loading growth data...')}</span>
        </div>
      </PageShell>
    )
  }

  // Error state
  if (error) {
    return (
      <PageShell width="wide" className="growth-page">
        <div className="gp-empty">
          <p>{tr('加载失败: {error}', 'Failed to load: {error}', { error })}</p>
        </div>
      </PageShell>
    )
  }

  // Empty state
  if (!dashboard || dashboard.overview.total_evaluations === 0) {
    return (
      <PageShell width="wide" className="growth-page">
        <div className="gp-empty">
          <div className="gp-empty-icon">
            <Sparkles size={48} strokeWidth={1.5} />
          </div>
          <h2>{tr('还没有能力评估数据', 'No competency evaluation data yet')}</h2>
          <p>
            {tr('在聊天室中与 AI 角色对话，然后点击"分析"按钮生成能力评估。', 'Chat with AI personas, then click “Analyze” to generate a competency evaluation.')}
            <br />
            {tr('完成 2 次以上评估后，就能看到成长趋势。', 'After 2 or more evaluations, growth trends will appear here.')}
          </p>
          <button className="gp-empty-btn" onClick={() => navigate('/chat')}>
            {tr('开始一场练习', 'Start a practice session')}
          </button>
        </div>
      </PageShell>
    )
  }

  const { evaluations, overview } = dashboard
  const radarData = buildRadarData(evaluations, tr)
  const dimChanges = computeDimensionChanges(evaluations)

  return (
    <PageShell width="wide" className="growth-page">
      {/* Gamification stats row */}
      <div className="gp-gamification-row">
        <div className="gp-gam-card">
          <div className="gp-gam-value">{xp}</div>
          <div className="gp-gam-label">
            <Zap size={11} /> {tr('总经验值', 'Total XP')}
          </div>
        </div>
        <div className="gp-gam-card">
          <div className="gp-gam-value">Lv.{levelInfo.level}</div>
          <div className="gp-gam-label">
            <Trophy size={11} /> {tr('等级', 'Level')}
          </div>
          <div className="gp-level-bar">
            <div
              className="gp-level-bar-fill"
              style={{ width: `${levelInfo.progress * 100}%` }}
            />
          </div>
        </div>
        <div className="gp-gam-card">
          <div className="gp-gam-value">{streak}</div>
          <div className="gp-gam-label">
            <Flame size={11} /> {tr('连续天数', 'Streak')}
          </div>
        </div>
        <div className="gp-gam-card">
          <div className="gp-gam-value">{overview.total_evaluations}</div>
          <div className="gp-gam-label">
            <Star size={11} /> {tr('评估次数', 'Evaluations')}
          </div>
        </div>
      </div>

      {/* 1. Overall Score Header */}
      <section className="gp-score-header">
        <div className="gp-score-header-top">
          <span className="gp-section-label">{tr('能力总览', 'Ability Overview')}</span>
        </div>

        <div className="gp-score-summary">
          <div className="gp-big-score">
            <span className="gp-big-score-value">
              {overview.latest_score.toFixed(1)}
            </span>
            <span className="gp-big-score-label">{tr('最新总分 / 5.0', 'Latest Total / 5.0')}</span>
          </div>

          <div className="gp-radar-container">
            <ResponsiveContainer width="100%" height={280}>
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
                <PolarGrid stroke="#e5e7eb" />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fontSize: 12, fill: '#6b7280' }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 5]}
                  tick={{ fontSize: 10 }}
                  tickCount={6}
                />
                <Tooltip />
                {evaluations.length > 1 && (
                  <Radar
                    name={tr('历史平均', 'Historical Average')}
                    dataKey="average"
                    stroke="#9ca3af"
                    fill="#9ca3af"
                    fillOpacity={0.15}
                    strokeDasharray="4 4"
                  />
                )}
                <Radar
                  name={tr('最新评估', 'Latest Evaluation')}
                  dataKey="latest"
                  stroke="var(--violet, #8B7EC8)"
                  fill="var(--violet, #8B7EC8)"
                  fillOpacity={0.25}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
            <div className="gp-radar-legend">
              <span className="gp-radar-legend-item">
                <span className="gp-radar-dot" style={{ background: 'var(--violet, #8B7EC8)' }} /> {tr('最新评估', 'Latest Evaluation')}
              </span>
              {evaluations.length > 1 && (
                <span className="gp-radar-legend-item">
                  <span className="gp-radar-dot dashed" /> {tr('历史平均', 'Historical Average')}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Week-over-week dimension changes */}
        {evaluations.length > 1 && Object.keys(dimChanges).length > 0 && (
          <div className="gp-dimension-changes">
            {DIMENSIONS.map((dim) => {
              const change = dimChanges[dim] ?? 0
              const arrow =
                change > 0 ? 'up' : change < 0 ? 'down' : 'same'
              return (
                <div key={dim} className="gp-dim-change">
                  <span className="gp-dim-change-name">
                    {getDimensionLabel(dim, tr)}
                  </span>
                  <span className={`gp-dim-change-arrow ${arrow}`}>
                    {arrow === 'up' && <><ArrowUp size={12} />+{change}</>}
                    {arrow === 'down' && <><ArrowDown size={12} />{change}</>}
                    {arrow === 'same' && <><Minus size={12} />0</>}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* 2. Skill Path Detail (vertical timeline) */}
      <section className="gp-skill-path">
        <h3 className="gp-skill-path-title">{tr('技能路径', 'Skill Path')}</h3>
        <div className="gp-timeline">
          {skillPath.map((node, idx) => {
            const status = getSkillStatus(node, idx, skillPath)
            const dim = node.dimension
            return (
              <div
                key={dim}
                className={`gp-timeline-node gp-timeline-node--${status}`}
              >
                <div className="gp-timeline-circle">
                  {status === 'completed' && <Check size={14} />}
                  {status === 'current' && <span className="gp-timeline-circle-dot" />}
                  {status === 'locked' && <Lock size={12} />}
                </div>
                <div className="gp-timeline-name">{tr(SKILL_NAMES[dim], SKILL_NAMES_EN[dim])}</div>
                <div className="gp-timeline-desc">
                  {tr(SKILL_DESCRIPTIONS[dim], SKILL_DESCRIPTIONS_EN[dim])}
                </div>
                {status === 'completed' && (
                  <div className="gp-timeline-status-badge completed">
                    <Check size={11} /> {tr('已完成 · 平均 {score}/5', 'Completed · Average {score}/5', { score: node.averageScore })}
                  </div>
                )}
                {status === 'current' && (
                  <div className="gp-timeline-suggestion">
                    <Sparkles size={12} /> {tr('推荐练习: {text}', 'Recommended practice: {text}', {
                      text: tr(SKILL_SUGGESTIONS[dim], SKILL_SUGGESTIONS_EN[dim]),
                    })}
                  </div>
                )}
                {status === 'locked' && (
                  <div className="gp-timeline-status-badge locked">
                    <Lock size={11} /> {tr(SKILL_UNLOCK_CONDITIONS[dim], SKILL_UNLOCK_CONDITIONS_EN[dim])}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* 3. Evaluation History */}
      <section className="gp-eval-history">
        <h3 className="gp-eval-history-title">{tr('评估历史', 'Evaluation History')}</h3>
        <div className="gp-eval-list">
          {evaluations.map((ev) => {
            const grade = scoreToGrade(ev.overall_score)
            const cls = gradeClass(ev.overall_score)
            const date = ev.created_at
              ? new Date(ev.created_at).toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US')
              : ''
            const feedback = buildFeedbackSummary(ev.scores, tr)
            return (
              <Link
                key={ev.id}
                to={`/chat/${ev.room_id}`}
                className="gp-eval-card"
              >
                <div className={`gp-eval-grade gp-eval-grade--${cls}`}>
                  {grade}
                </div>
                <div className="gp-eval-info">
                  <span className="gp-eval-name">
                    {ev.room_name || tr('评估 #{id}', 'Evaluation #{id}', { id: ev.id })}
                  </span>
                  <span className="gp-eval-meta">
                    {date} &middot; {tr('总分 {score}/5', 'Total {score}/5', { score: ev.overall_score.toFixed(1) })}
                  </span>
                  {feedback && (
                    <span className="gp-eval-feedback">{feedback}</span>
                  )}
                </div>
                <ChevronRight size={16} className="gp-eval-arrow" />
              </Link>
            )
          })}
        </div>
      </section>

      {/* 4. Profile Card */}
      <section className="gp-profile-section">
        <div className="gp-profile-header">
          <h3 className="gp-profile-title">{tr('沟通力名片', 'Communication Profile Card')}</h3>
          {profileCard && (
            <button
              className="gp-download-btn"
              onClick={handleDownload}
              disabled={downloading}
            >
              {downloading ? (
                <Loader2 size={14} className="gp-spin" />
              ) : (
                <Download size={14} />
              )}
              {downloading ? tr('生成中...', 'Generating...') : tr('下载为图片', 'Download Image')}
            </button>
          )}
        </div>

        {!profileCard ? (
          <div className="gp-profile-placeholder">
            <button
              className="gp-generate-card-btn"
              onClick={handleGenerateCard}
              disabled={profileCardLoading || overview.total_evaluations < 2}
              title={
                overview.total_evaluations < 2
                  ? tr('再完成 {count} 次练习即可解锁', 'Complete {count} more practice sessions to unlock', {
                    count: 2 - overview.total_evaluations,
                  })
                  : tr('生成沟通力名片', 'Generate communication profile card')
              }
            >
              {profileCardLoading ? (
                <Loader2 size={14} className="gp-spin" />
              ) : (
                <Share2 size={14} />
              )}
              {profileCardLoading ? tr('生成中...', 'Generating...') : tr('生成我的名片', 'Generate My Card')}
            </button>
          </div>
        ) : (
          <div className="gp-profile-card-wrapper">
            <ProfileCard data={profileCard} cardRef={cardRef} />
          </div>
        )}
      </section>
    </PageShell>
  )
}

export default GrowthPage
