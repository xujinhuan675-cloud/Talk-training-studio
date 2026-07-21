import { Download, X } from 'lucide-react'
import { useRef, useState } from 'react'
import html2canvas from 'html2canvas'
import { type ProfileCard as ProfileCardData } from '../services/api'
import ProfileCard from './ProfileCard'
import { useI18n } from '../i18n'
import { Button } from './ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogTitle,
} from './ui/dialog'
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
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose()
      }}
    >
      <DialogContent className="pc-dialog" aria-describedby={undefined}>
        {/* Dialog header - outside cardRef, not captured in PNG */}
        <div className="pc-dialog-header">
          <DialogTitle className="pc-dialog-title">
            {tr('我的沟通力名片', 'My Communication Profile Card')}
          </DialogTitle>
          <DialogClose asChild>
            <Button
              aria-label={tr('关闭', 'Close')}
              className="pc-close-btn"
              size="icon"
              variant="ghost"
            >
              <X aria-hidden="true" size={18} />
            </Button>
          </DialogClose>
        </div>

        {/* Card area captured by html2canvas */}
        <div className="pc-card-wrapper">
          <ProfileCard data={data} cardRef={cardRef} />
        </div>

        {/* Footer buttons - outside cardRef, not captured in PNG */}
        <div className="pc-footer">
          <Button
            className="pc-btn-download"
            onClick={handleDownload}
            disabled={downloading}
            variant="primary"
          >
            <Download aria-hidden="true" size={16} />
            {downloading ? t('common.generating') : t('common.downloadImage')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
