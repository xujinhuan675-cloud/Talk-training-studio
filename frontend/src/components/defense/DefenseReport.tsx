import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import type { DefenseReport as DefenseReportData } from '../../services/api'
import { useI18n } from '../../i18n'
import './DefenseReport.css'

interface Props {
  report: DefenseReportData
}

interface RadarDataPoint {
  dimension: string
  score: number
}

function buildRadarData(dimensionScores: Record<string, number>): RadarDataPoint[] {
  return Object.entries(dimensionScores).map(([dim, score]) => ({
    dimension: dim,
    score,
  }))
}

function scoreClass(score: number): string {
  if (score >= 80) return 'high'
  if (score >= 60) return 'mid'
  return 'low'
}

function scoreBadgeClass(score: number): string {
  if (score >= 80) return 'dr-review-score-badge--high'
  if (score >= 60) return 'dr-review-score-badge--mid'
  return 'dr-review-score-badge--low'
}

export default function DefenseReport({ report }: Props) {
  const { tr } = useI18n()
  const radarData = buildRadarData(report.dimension_scores)

  return (
    <div className="dr-container">
      {/* Overall score hero */}
      <div className="dr-score-hero">
        <span className={`dr-score-number dr-score-number--${scoreClass(report.overall_score)}`}>
          {report.overall_score}
        </span>
        <span className="dr-score-label">{tr('综合得分', 'Overall Score')}</span>
      </div>

      {/* Radar chart */}
      {radarData.length > 0 && (
        <div className="dr-radar-section">
          <h3 className="dr-section-title">{tr('维度评分', 'Dimension Scores')}</h3>
          <div className="dr-radar-wrapper">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
                <PolarGrid stroke="var(--border)" />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
                />
                <PolarRadiusAxis
                  angle={30}
                  domain={[0, 100]}
                  tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                />
                <Radar
                  name={tr('得分', 'Score')}
                  dataKey="score"
                  stroke="var(--violet)"
                  fill="var(--violet)"
                  fillOpacity={0.25}
                  strokeWidth={2}
                />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="dr-summary-section">
        <h3 className="dr-section-title">{tr('综合评价', 'Overall Evaluation')}</h3>
        <p className="dr-summary-text">{report.summary}</p>
      </div>

      {/* Top improvements */}
      {report.top_improvements.length > 0 && (
        <div className="dr-improvements-section">
          <h3 className="dr-section-title">{tr('重点改进方向', 'Key Improvement Areas')}</h3>
          <ul className="dr-improvements-list">
            {report.top_improvements.map((item, i) => (
              <li key={i} className="dr-improvement-item">
                <span className="dr-improvement-bullet">{i + 1}</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Question reviews */}
      {report.question_reviews.length > 0 && (
        <div className="dr-reviews-section">
          <h3 className="dr-section-title">{tr('逐题点评', 'Question-by-question Review')}</h3>
          <div className="dr-review-list">
            {report.question_reviews.map((review, i) => (
              <div key={i} className="dr-review-card">
                <div className="dr-review-header">
                  <span className="dr-review-question">
                    {i + 1}. {review.question}
                  </span>
                  <span className={`dr-review-score-badge ${scoreBadgeClass(review.score)}`}>
                    {review.score}
                  </span>
                </div>
                <div className="dr-review-answer">
                  <span className="dr-review-answer-label">{tr('回答摘要:', 'Answer Summary:')}</span>
                  {review.user_answer_summary}
                </div>
                <div className="dr-review-feedback">
                  <span className="dr-review-feedback-label">{tr('点评:', 'Feedback:')}</span>
                  {review.feedback}
                </div>
                <div className="dr-review-improvement">
                  <span className="dr-review-improvement-label">{tr('改进建议:', 'Improvement:')}</span>
                  {review.improvement}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
