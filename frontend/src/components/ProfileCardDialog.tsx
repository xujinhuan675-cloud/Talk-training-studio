import { useRef, useState } from 'react'
import html2canvas from 'html2canvas'
import { type ProfileCard as ProfileCardData } from '../services/api'
import ProfileCard from './ProfileCard'
import { useI18n } from '../i18n'
import './ProfileCard.css'

interface Props {
  open: boolean
  onClose: () => void
  data: ProfileCardData | null
}

export default function ProfileCardDialog({ open, onClose, data }: Props) {
  const { t, tr } = useI18n()
  const cardRef = useRef<HTMLDivElement>(null)
  const [downloading, setDownloading] = useState(false)

  if (!open || !data) return null

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

  return (
    <div className="pc-overlay" onClick={onClose}>
      <div className="pc-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Dialog header — outside cardRef, not captured in PNG */}
        <div className="pc-dialog-header">
          <h2 className="pc-dialog-title">{tr('我的沟通力名片', 'My Communication Profile Card')}</h2>
          <button className="pc-close-btn" onClick={onClose} aria-label={tr('关闭', 'Close')}>
            ✕
          </button>
        </div>

        {/* Card area captured by html2canvas */}
        <div className="pc-card-wrapper">
          <ProfileCard data={data} cardRef={cardRef} />
        </div>

        {/* Footer buttons — outside cardRef, not captured in PNG */}
        <div className="pc-footer">
          <button className="pc-btn-download" onClick={handleDownload} disabled={downloading}>
            {downloading ? t('common.generating') : t('common.downloadImage')}
          </button>
        </div>
      </div>
    </div>
  )
}
