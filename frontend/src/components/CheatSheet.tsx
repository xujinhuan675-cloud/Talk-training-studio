import { useRef, useState } from 'react'
import html2canvas from 'html2canvas'
import { type CheatSheet } from '../services/api'
import { useI18n } from '../i18n'
import './CheatSheet.css'

interface Props {
  open: boolean
  onClose: () => void
  data: CheatSheet | null
  personaName: string
}

export default function CheatSheetDialog({ open, onClose, data, personaName }: Props) {
  const { t, tr } = useI18n()
  const cardRef = useRef<HTMLDivElement>(null)
  const [downloading, setDownloading] = useState(false)

  if (!open || !data) return null

  const handleCopy = () => {
    const lines: string[] = []
    lines.push(tr('话术纸条 — 与{name}的对话', 'Cheat Sheet — Conversation with {name}', { name: personaName }))
    lines.push('')
    lines.push(tr('【开场白】', '[Opening]'))
    lines.push(data.opening)
    lines.push('')
    lines.push(tr('【关键话术】', '[Key Tactics]'))
    data.key_tactics.forEach((t) => {
      lines.push(tr('当对方：{text}', 'When they say: {text}', { text: t.situation }))
      lines.push(tr('→ 你应该：{text}', '→ You should: {text}', { text: t.response }))
    })
    lines.push('')
    lines.push(tr('【避坑提醒】', '[Pitfalls]'))
    data.pitfalls.forEach((p) => {
      lines.push(`✗ ${p}`)
    })
    lines.push('')
    lines.push(tr('【底线策略】', '[Bottom Line]'))
    lines.push(data.bottom_line)

    navigator.clipboard.writeText(lines.join('\n')).catch(() => {
      // silently ignore clipboard errors
    })
  }

  const handleDownload = async () => {
    const el = cardRef.current
    if (!el) return
    setDownloading(true)
    try {
      // Temporarily remove overflow clipping so html2canvas captures full content
      el.classList.add('cs-card--capturing')
      const canvas = await html2canvas(el, {
        scale: 2,
        backgroundColor: '#fff',
        scrollY: 0,
        scrollX: 0,
        height: el.scrollHeight,
        windowHeight: el.scrollHeight,
      })
      el.classList.remove('cs-card--capturing')
      const link = document.createElement('a')
      link.download = tr('话术纸条.png', 'cheat-sheet.png')
      link.href = canvas.toDataURL('image/png')
      link.click()
    } finally {
      const el2 = cardRef.current
      if (el2) el2.classList.remove('cs-card--capturing')
      setDownloading(false)
    }
  }

  return (
    <div className="cs-overlay" onClick={onClose}>
      <div className="cs-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Card area captured by html2canvas */}
        <div className="cs-card" ref={cardRef}>
          {/* Header */}
          <div className="cs-header">
            <div className="cs-header-left">
              <h2 className="cs-title">{tr('话术纸条', 'Cheat Sheet')}</h2>
              {personaName && (
                <span className="cs-persona-badge">{personaName}</span>
              )}
            </div>
            <button className="cs-close-btn" onClick={onClose} aria-label={tr('关闭', 'Close')}>
              ✕
            </button>
          </div>

          {/* Opening */}
          <div className="cs-section-opening">
            <p className="cs-section-title">💬 {tr('开场白', 'Opening')}</p>
            <div className="cs-opening-box">{data.opening}</div>
          </div>

          {/* Key tactics */}
          <div className="cs-section-tactics">
            <p className="cs-section-title">⚡ {tr('关键话术', 'Key Tactics')}</p>
            <div className="cs-tactic-list">
              {data.key_tactics.map((tactic, i) => (
                <div key={i} className="cs-tactic-item">
                  <span className="cs-tactic-situation">{tr('当对方：{text}', 'When they say: {text}', { text: tactic.situation })}</span>
                  <span className="cs-tactic-response">
                    <span className="cs-tactic-arrow">→</span> {tactic.response}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Pitfalls */}
          <div className="cs-section-pitfalls">
            <p className="cs-section-title">⚠️ {tr('避坑提醒', 'Pitfalls')}</p>
            <div className="cs-pitfall-list">
              {data.pitfalls.map((pitfall, i) => (
                <div key={i} className="cs-pitfall-item">✗ {pitfall}</div>
              ))}
            </div>
          </div>

          {/* Bottom line */}
          <div className="cs-section-bottomline">
            <p className="cs-section-title">🛡️ {tr('底线策略', 'Bottom Line')}</p>
            <div className="cs-bottomline-box">{data.bottom_line}</div>
          </div>
        </div>

        {/* Footer buttons — outside cardRef, not captured in PNG */}
        <div className="cs-footer">
          <button className="cs-btn-copy" onClick={handleCopy}>
            {tr('复制全文', 'Copy All')}
          </button>
          <button className="cs-btn-download" onClick={handleDownload} disabled={downloading}>
            {downloading ? t('common.generating') : t('common.downloadImage')}
          </button>
        </div>
      </div>
    </div>
  )
}
