import { X } from 'lucide-react'
import type { AnalysisReport, AnalysisReportSummary, TrainingDimensionScore } from '../../services/api'
import { useI18n } from '../../i18n'
import './AnalysisPanel.css'

export interface AnalysisPanelProps {
  result: AnalysisReport
  reportList: AnalysisReportSummary[]
  analyzingRoom: boolean
  onClose: () => void
  onSelectReport: (reportId: number) => void
  onGenerateNewReport: () => void
  onScrollToMessage: (
    messageIndices: number[] | undefined,
    messageIdMap: Record<string, number> | undefined,
  ) => void
}

function hasDimensionContent(dimension: TrainingDimensionScore | null | undefined): dimension is TrainingDimensionScore {
  return Boolean(dimension && dimension.status !== 'not_applicable')
}

export default function AnalysisPanel({
  result,
  reportList,
  analyzingRoom,
  onClose,
  onSelectReport,
  onGenerateNewReport,
  onScrollToMessage,
}: AnalysisPanelProps) {
  const { tr, locale } = useI18n()
  const videoDimensions: Array<{
    key: string
    title: string
    value: TrainingDimensionScore
  }> = [
    {
      key: 'content_delivery',
      title: tr('内容表达', 'Content delivery'),
      value: result.content.content_delivery,
    },
    {
      key: 'camera_presence',
      title: tr('镜头表现', 'Camera presence'),
      value: result.content.camera_presence,
    },
  ].flatMap((item) => hasDimensionContent(item.value) ? [{ ...item, value: item.value }] : [])

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog analysis-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="analysis-header">
          <h3>{tr('对话分析报告', 'Conversation Analysis Report')}</h3>
          <button className="analysis-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Historical report selector */}
        {reportList.length > 1 && (
          <div className="analysis-report-selector">
            <select
              value={result.id}
              onChange={(e) => onSelectReport(Number(e.target.value))}
            >
              {reportList.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.created_at ? new Date(r.created_at).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US') : tr('报告 #{id}', 'Report #{id}', { id: r.id })}
                </option>
              ))}
            </select>
            <button
              className="analysis-new-btn"
              onClick={onGenerateNewReport}
              disabled={analyzingRoom}
            >
              {analyzingRoom ? tr('生成中...', 'Generating...') : tr('+ 新报告', '+ New Report')}
            </button>
          </div>
        )}
        {reportList.length <= 1 && (
          <div className="analysis-report-selector">
            <span className="analysis-report-date">
              {result.created_at ? new Date(result.created_at).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US') : ''}
            </span>
            <button
              className="analysis-new-btn"
              onClick={onGenerateNewReport}
              disabled={analyzingRoom}
            >
              {analyzingRoom ? tr('生成中...', 'Generating...') : tr('重新分析', 'Analyze Again')}
            </button>
          </div>
        )}

        <p className="analysis-summary">{result.summary}</p>

        {videoDimensions.length > 0 && (
          <div className="analysis-section">
            <h4>{tr('视频级复盘', 'Video Review')}</h4>
            <div className="analysis-cards">
              {videoDimensions.map((item) => {
                const dimension = item.value
                const hasLinks = dimension.message_indices && dimension.message_indices.length > 0 && result.content.message_id_map
                return (
                  <div
                    key={item.key}
                    className={`analysis-card${hasLinks ? ' clickable' : ''}`}
                    onClick={() => hasLinks && onScrollToMessage(dimension.message_indices, result.content.message_id_map)}
                  >
                    <div className="analysis-card-header">
                      <span className="analysis-card-name">{item.title}</span>
                      <span className={`analysis-card-score ${dimension.status === 'observed' ? 'positive' : 'neutral'}`}>
                        {dimension.score === null || dimension.score === undefined ? tr('待补充', 'Pending') : dimension.score}
                      </span>
                    </div>
                    <div className="analysis-card-body">{dimension.rationale || dimension.label}</div>
                    {dimension.suggestions.length > 0 && (
                      <div className="analysis-card-body">
                        {dimension.suggestions.slice(0, 2).join(' / ')}
                      </div>
                    )}
                    {dimension.status === 'placeholder' && (
                      <div className="analysis-card-link">{tr('已预留结构化评分，等待视频表现分析接入', 'Structured score reserved; video performance analysis is not connected yet')}</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Resistance ranking cards */}
        {result.content.resistance_ranking.length > 0 && (
          <div className="analysis-section">
            <h4>{tr('阻力排名', 'Resistance Ranking')}</h4>
            <div className="analysis-cards">
              {result.content.resistance_ranking.map((item, i) => {
                const hasLinks = item.message_indices && item.message_indices.length > 0 && result.content.message_id_map
                return (
                  <div
                    key={i}
                    className={`analysis-card${hasLinks ? ' clickable' : ''}`}
                    onClick={() => hasLinks && onScrollToMessage(item.message_indices, result.content.message_id_map)}
                  >
                    <div className="analysis-card-header">
                      <span className="analysis-card-name">{item.persona_name}</span>
                      <span className={`analysis-card-score ${item.score >= 0 ? 'positive' : 'negative'}`}>
                        {item.score > 0 ? '+' : ''}{item.score}
                      </span>
                    </div>
                    <div className="analysis-card-body">{item.reason}</div>
                    {hasLinks && (
                      <div className="analysis-card-link">{tr('点击查看对话原文 →', 'Click to view source messages →')}</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Effective arguments cards */}
        {result.content.effective_arguments.length > 0 && (
          <div className="analysis-section">
            <h4>{tr('有效论点', 'Effective Arguments')}</h4>
            <div className="analysis-cards">
              {result.content.effective_arguments.map((item, i) => {
                const hasLinks = item.message_indices && item.message_indices.length > 0 && result.content.message_id_map
                return (
                  <div
                    key={i}
                    className={`analysis-card argument${hasLinks ? ' clickable' : ''}`}
                    onClick={() => hasLinks && onScrollToMessage(item.message_indices, result.content.message_id_map)}
                  >
                    <div className="analysis-card-header">
                      <span className="analysis-card-argument">{item.argument}</span>
                      <span className="analysis-card-target">→ {item.target_persona}</span>
                    </div>
                    <div className="analysis-card-body">{item.effectiveness}</div>
                    {hasLinks && (
                      <div className="analysis-card-link">{tr('点击查看对话原文 →', 'Click to view source messages →')}</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Communication suggestions */}
        {result.content.communication_suggestions.length > 0 && (
          <div className="analysis-section">
            <h4>{tr('沟通建议', 'Communication Suggestions')}</h4>
            <div className="analysis-cards">
              {result.content.communication_suggestions.map((item, i) => (
                <div key={i} className="analysis-card suggestion">
                  <div className="analysis-card-header">
                    <span className="analysis-card-name">{item.persona_name}</span>
                    <span className={`suggestion-priority ${item.priority}`}>{item.priority}</span>
                  </div>
                  <div className="analysis-card-body">{item.suggestion}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
