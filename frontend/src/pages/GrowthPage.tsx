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
} from 'lucide-react'
import { useGrowth, type SkillPathNode, type DimensionKey } from '../hooks/useGrowth'
import { generateProfileCard, type ProfileCard as ProfileCardData } from '../services/api'
import ProfileCard from '../components/ProfileCard'
import { useI18n, type Translate, type TranslateInline, type TranslationKey } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import { PageShell } from '../components/ui/page'
import './GrowthPage.css'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DIMENSIONS: DimensionKey[] = [
  'persuasion',
  'emotional_management',
  'active_listening',
  'structured_expression',
  'conflict_resolution',
  'stakeholder_alignment',
]
const DIMENSION_SET = new Set<string>(DIMENSIONS)
const RECENT_EVALUATION_LIMIT = 5

function isDimensionKey(value: string | undefined): value is DimensionKey {
  return Boolean(value && DIMENSION_SET.has(value))
}

function growthDimensionLabelKey(dim: DimensionKey): TranslationKey {
  return `growth.dimension.${dim}.label` as TranslationKey
}

function growthSkillKey(dim: DimensionKey, field: 'name' | 'desc' | 'unlock' | 'suggestion'): TranslationKey {
  return `growth.skill.${dim}.${field}` as TranslationKey
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
  t: Translate,
): RadarDataPoint[] {
  return DIMENSIONS.map((dim) => {
    const latest = evaluations.length > 0 ? (evaluations[0].scores[dim]?.score ?? 0) : 0
    const allScores = evaluations.map((ev) => ev.scores[dim]?.score ?? 0).filter((s) => s > 0)
    const average =
      allScores.length > 0
        ? Math.round((allScores.reduce((a, b) => a + b, 0) / allScores.length) * 10) / 10
        : 0
    return { dimension: t(growthDimensionLabelKey(dim)), latest, average }
  })
}

function getDimensionLabel(dim: string | undefined, t: Translate): string {
  return isDimensionKey(dim) ? t(growthDimensionLabelKey(dim)) : dim || ''
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
  t: Translate,
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
  const bestLabel = getDimensionLabel(best?.[0], t)
  const worstLabel = getDimensionLabel(worst?.[0], t)
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
  const { t, tr, locale } = useI18n()
  const {
    dashboard,
    loading,
    error,
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
          <h2>{tr('暂无评估数据', 'No evaluation data yet')}</h2>
          <p>{tr('完成一次练习并生成评估后，这里会显示总览和趋势。', 'Complete one practice and generate an evaluation to see the overview and trends.')}</p>
          <button className="gp-empty-btn" onClick={() => navigate(APP_ROUTES.practiceScenarios)}>
            {t('common.startPractice')}
          </button>
        </div>
      </PageShell>
    )
  }

  const { evaluations, overview } = dashboard
  const radarData = buildRadarData(evaluations, t)
  const dimChanges = computeDimensionChanges(evaluations)
  const recentEvaluations = evaluations.slice(0, RECENT_EVALUATION_LIMIT)

  return (
    <PageShell width="wide" className="growth-page">
      {/* 1. Overall Score Header */}
      <section className="gp-score-header">
        <div className="gp-score-header-top">
          <span className="gp-section-label">{tr('能力总览', 'Ability Overview')}</span>
          <div className="gp-score-header-actions">
            <span className="gp-section-count">
              {tr('{count} 次评估', '{count} evaluations', { count: overview.total_evaluations })}
            </span>
            <Link to={APP_ROUTES.growthLeaderboard} className="gp-section-link">
              {t('common.teamBoard')}
              <ChevronRight size={14} />
            </Link>
          </div>
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
                  stroke="var(--green, #0F766E)"
                  fill="var(--green, #0F766E)"
                  fillOpacity={0.25}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
            <div className="gp-radar-legend">
              <span className="gp-radar-legend-item">
                <span className="gp-radar-dot" style={{ background: 'var(--green, #0F766E)' }} /> {tr('最新评估', 'Latest Evaluation')}
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
                    {getDimensionLabel(dim, t)}
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

      {/* 2. Evaluation History */}
      <section className="gp-eval-history">
        <div className="gp-section-heading">
          <h3 className="gp-eval-history-title">{tr('近期复盘', 'Recent reviews')}</h3>
          <Link to={APP_ROUTES.reviewSessions} className="gp-section-link">
            {t('common.viewAllReviews')}
            <ChevronRight size={14} />
          </Link>
        </div>
        <div className="gp-eval-list">
          {recentEvaluations.map((ev) => {
            const grade = scoreToGrade(ev.overall_score)
            const cls = gradeClass(ev.overall_score)
            const date = ev.created_at
              ? new Date(ev.created_at).toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US')
              : ''
            const feedback = buildFeedbackSummary(ev.scores, t, tr)
            return (
              <Link
                key={ev.id}
                to={APP_ROUTES.conversation(ev.room_id)}
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

      {/* 3. Skill Path Detail (vertical timeline) */}
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
                <div className="gp-timeline-name">{t(growthSkillKey(dim, 'name'))}</div>
                <div className="gp-timeline-desc">
                  {t(growthSkillKey(dim, 'desc'))}
                </div>
                {status === 'completed' && (
                  <div className="gp-timeline-status-badge completed">
                    <Check size={11} /> {tr('已完成 · 平均 {score}/5', 'Completed · Average {score}/5', { score: node.averageScore })}
                  </div>
                )}
                {status === 'current' && (
                  <Link to={APP_ROUTES.practiceScenarios} className="gp-timeline-suggestion">
                    <Sparkles size={12} /> {tr('推荐练习: {text}', 'Recommended practice: {text}', {
                      text: t(growthSkillKey(dim, 'suggestion')),
                    })}
                  </Link>
                )}
                {status === 'locked' && (
                  <div className="gp-timeline-status-badge locked">
                    <Lock size={11} /> {t(growthSkillKey(dim, 'unlock'))}
                  </div>
                )}
              </div>
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
              {downloading ? t('common.generating') : tr('下载为图片', 'Download Image')}
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
              {profileCardLoading ? t('common.generating') : tr('生成我的名片', 'Generate My Card')}
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
