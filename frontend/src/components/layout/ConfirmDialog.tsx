import { AlertTriangle } from 'lucide-react'
import { useI18n } from '../../i18n'
import './ConfirmDialog.css'

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { tr } = useI18n()

  if (!open) return null

  return (
    <div className="confirm-overlay" onClick={onCancel}>
      <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <div className={`confirm-icon ${danger ? 'danger' : ''}`}>
          <AlertTriangle size={22} />
        </div>
        <h3 className="confirm-title">{title}</h3>
        <p className="confirm-message">{message}</p>
        <div className="confirm-actions">
          <button className="confirm-btn cancel" onClick={onCancel}>
            {cancelLabel || tr('取消', 'Cancel')}
          </button>
          <button
            className={`confirm-btn ${danger ? 'danger' : 'primary'}`}
            onClick={onConfirm}
            autoFocus
          >
            {confirmLabel || tr('确定', 'OK')}
          </button>
        </div>
      </div>
    </div>
  )
}
