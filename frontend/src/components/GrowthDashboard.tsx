import { useEffect, useState } from 'react'
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import Markdown from 'react-markdown'
import { Sparkles, Loader2, Share2 } from 'lucide-react'
import {
  fetchGrowthDashboard,
  generateGrowthInsight,
  generateProfileCard,
  type GrowthDashboard as GrowthDashboardData,
  type ProfileCard as ProfileCardData,
} from '../services/api'
import ProfileCardDialog from './ProfileCardDialog'
import { useI18n, type Translate } from '../i18n'
import { GROWTH_DIMENSIONS, getGrowthDimensionLabel } from '../utils/growthLabels'
import './GrowthDashboard.css'

interface RadarDataPoint {
  dimension: string
  latest: number
  average: number
}

function buildRadarData(dashboard: GrowthDashboardData, t: Translate): RadarDataPoint[] {
  const evals = dashboard.evaluations
  return GROWTH_DIMENSIONS.map((dim) => {
    const latest = evals.length > 0 ? (evals[0].scores[dim]?.score ?? 0) : 0
    const allScores = evals.map((ev) => ev.scores[dim]?.score ?? 0).filter((s) => s > 0)
    const average = allScores.length > 0 ? Math.round((allScores.reduce((a, b) => a + b, 0) / allScores.length) * 10) / 10 : 0
    return { dimension: getGrowthDimensionLabel(dim, t), latest, average }
  })
}

function scoreColor(score: number): string {
  if (score >= 4) return '#16a34a'
  if (score >= 3) return '#d97706'
  return '#dc2626'
}

interface Props {
  onCreateRoom: () => void
}

export default function GrowthDashboard({ onCreateRoom }: Props) {
  const { t, tr, locale } = useI18n()
  const [data, setData] = useState<GrowthDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [insight, setInsight] = useState<string | null>(null)
  const [insightLoading, setInsightLoading] = useState(false)
  const [profileCard, setProfileCard] = useState<ProfileCardData | null>(null)
  const [profileCardLoading, setProfileCardLoading] = useState(false)
  const [showProfileCard, setShowProfileCard] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetchGrowthDashboard()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const handleGenerateCard = async () => {
    setProfileCardLoading(true)
    try {
      const card = await generateProfileCard()
      setProfileCard(card)
      setShowProfileCard(true)
    } catch (e) {
      console.error(e)
    } finally {
      setProfileCardLoading(false)
    }
  }

  const handleGenerateInsight = async () => {
    setInsightLoading(true)
    try {
      const text = await generateGrowthInsight()
      setInsight(text)
    } catch (e) {
      console.error(e)
    } finally {
      setInsightLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="growth-dashboard">
        <div className="growth-loading">
          <Loader2 size={24} className="spin" />
          <span>{tr('加载成长数据...', 'Loading growth data...')}</span>
        </div>
      </div>
    )
  }

  if (!data || data.overview.total_evaluations === 0) {
    return (
      <div className="growth-dashboard">
        <div className="growth-empty">
          <div className="growth-empty-icon">
            <Sparkles size={48} strokeWidth={1.5} />
          </div>
          <h2>{tr('还没有能力评估数据', 'No competency evaluation data yet')}</h2>
          <p>{tr('在聊天室中与 AI 角色对话，然后点击"分析"按钮生成能力评估。', 'Chat with AI personas, then click “Analyze” to generate a competency evaluation.')}<br />{tr('完成 2 次以上评估后，就能看到成长趋势。', 'After 2 or more evaluations, growth trends will appear here.')}</p>
          <button className="growth-cta" onClick={onCreateRoom}>
            {tr('开始一场练习', 'Start a practice session')}
          </button>
        </div>
      </div>
    )
  }

  const radarData = buildRadarData(data, t)
  const { overview, evaluations } = data

  return (
    <div className="growth-dashboard">
      <h2 className="growth-title">{tr('成长轨迹', 'Growth Trajectory')}</h2>

      {/* Stats cards */}
      <div className="growth-stats">
        <div className="stat-card">
          <div className="stat-value">{overview.total_sessions}</div>
          <div className="stat-label">{tr('练习次数', 'Practice Sessions')}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overview.total_evaluations}</div>
          <div className="stat-label">{tr('评估次数', 'Evaluations')}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: scoreColor(overview.avg_overall_score) }}>
            {overview.avg_overall_score.toFixed(1)}
          </div>
          <div className="stat-label">{tr('平均分', 'Average Score')}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: scoreColor(overview.latest_score) }}>
            {overview.latest_score.toFixed(1)}
          </div>
          <div className="stat-label">{tr('最新分', 'Latest Score')}</div>
        </div>
      </div>

      {/* Radar chart */}
      <div className="growth-radar-section">
        <h3>{tr('能力雷达图', 'Ability Radar')}</h3>
        <div className="growth-radar-wrapper">
          <ResponsiveContainer width="100%" height={320}>
            <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
              <PolarGrid stroke="#e5e7eb" />
              <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12, fill: '#6b7280' }} />
              <PolarRadiusAxis angle={90} domain={[0, 5]} tick={{ fontSize: 10 }} tickCount={6} />
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
                stroke="#0F766E"
                fill="#0F766E"
                fillOpacity={0.25}
                strokeWidth={2}
              />
            </RadarChart>
          </ResponsiveContainer>
          <div className="radar-legend">
            <span className="radar-legend-item">
              <span className="radar-dot" style={{ background: '#0F766E' }} /> {tr('最新评估', 'Latest Evaluation')}
            </span>
            {evaluations.length > 1 && (
              <span className="radar-legend-item">
                <span className="radar-dot dashed" /> {tr('历史平均', 'Historical Average')}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Dimension trends as table */}
      {evaluations.length > 1 && (
        <div className="dimension-trends">
          <h3>{tr('各维度趋势对比', 'Dimension Trend Comparison')}</h3>
          <div className="trends-table-wrap">
            <table className="trends-table">
              <thead>
                <tr>
                  <th>{tr('维度', 'Dimension')}</th>
                  {evaluations.map((ev, i) => (
                    <th key={ev.id}>
                      <div className="trends-th-room">{ev.room_name || `#${i + 1}`}</div>
                      <div className="trends-th-date">
                        {ev.created_at ? new Date(ev.created_at).toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US') : ''}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {GROWTH_DIMENSIONS.map((dim) => (
                  <tr key={dim}>
                    <td className="trends-dim-name">{getGrowthDimensionLabel(dim, t)}</td>
                    {evaluations.map((ev) => {
                      const sc = ev.scores[dim]?.score ?? 0
                      return (
                        <td key={ev.id} className="trends-score-cell">
                          <span className="trends-score-badge" style={{ background: scoreColor(sc) + '20', color: scoreColor(sc) }}>
                            {sc}
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
                <tr className="trends-total-row">
                  <td className="trends-dim-name">{tr('总分', 'Total')}</td>
                  {evaluations.map((ev) => (
                    <td key={ev.id} className="trends-score-cell">
                      <strong style={{ color: scoreColor(ev.overall_score) }}>
                        {ev.overall_score.toFixed(1)}
                      </strong>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Latest evaluation detail */}
      {evaluations.length > 0 && (
        <div className="growth-detail">
          <h3>{tr('最新评估详情', 'Latest Evaluation Detail')}</h3>
          <div className="detail-meta">
            {evaluations[0].room_name} &middot; {tr('总分 {score}/5', 'Total {score}/5', { score: evaluations[0].overall_score.toFixed(1) })}
          </div>
          {GROWTH_DIMENSIONS.map((dim) => {
            const sc = evaluations[0].scores[dim]
            if (!sc) return null
            return (
              <div key={dim} className="detail-item">
                <div className="detail-dim-header">
                  <span className="detail-dim-name">{getGrowthDimensionLabel(dim, t)}</span>
                  <span className="detail-dim-score" style={{ color: scoreColor(sc.score) }}>
                    {sc.score}/5
                  </span>
                </div>
                {sc.evidence && <div className="detail-evidence">{sc.evidence}</div>}
                {sc.suggestion && <div className="detail-suggestion">{sc.suggestion}</div>}
              </div>
            )
          })}
        </div>
      )}

      {/* Growth insight */}
      <div className="growth-insight-section">
        <div className="insight-header">
          <h3>{tr('成长洞察', 'Growth Insights')}</h3>
          <button
            className="insight-btn"
            onClick={handleGenerateInsight}
            disabled={insightLoading}
          >
            {insightLoading ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />}
            {insightLoading ? t('common.generating') : tr('生成洞察', 'Generate Insights')}
          </button>
        </div>
        {insightLoading && (
          <div className="insight-loading">
            <Loader2 size={20} className="spin" />
            <span>{tr('AI 正在分析你的成长轨迹...', 'AI is analyzing your growth trajectory...')}</span>
          </div>
        )}
        {insight && !insightLoading && (
          <div className="growth-insight-content">
            <Markdown>{insight}</Markdown>
          </div>
        )}
      </div>

      {/* Profile Card */}
      <div className="growth-card-section">
        <button
          className="profile-card-btn"
          onClick={handleGenerateCard}
          disabled={profileCardLoading || data.overview.total_evaluations < 2}
          title={data.overview.total_evaluations < 2
            ? tr('再完成 {count} 次练习即可解锁', 'Complete {count} more practice sessions to unlock', { count: 2 - data.overview.total_evaluations })
            : tr('生成沟通力名片', 'Generate communication profile card')}
        >
          {profileCardLoading ? <Loader2 size={14} className="spin" /> : <Share2 size={14} />}
          {profileCardLoading ? t('common.generating') : tr('生成我的名片', 'Generate My Card')}
        </button>
      </div>

      <ProfileCardDialog
        open={showProfileCard}
        onClose={() => setShowProfileCard(false)}
        data={profileCard}
      />
    </div>
  )
}
