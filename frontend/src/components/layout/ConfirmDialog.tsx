import { AlertTriangle } from 'lucide-react'
import { useI18n } from '../../i18n'
import { Button } from '../ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '../ui/dialog'
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

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onCancel()
      }}
    >
      <DialogContent className="confirm-dialog">
        <div className={`confirm-icon ${danger ? 'danger' : ''}`}>
          <AlertTriangle size={22} aria-hidden="true" />
        </div>
        <DialogTitle className="confirm-title">{title}</DialogTitle>
        <DialogDescription className="confirm-message">{message}</DialogDescription>
        <div className="confirm-actions">
          <Button className="confirm-btn" variant="secondary" onClick={onCancel}>
            {cancelLabel || tr('取消', 'Cancel')}
          </Button>
          <Button
            className="confirm-btn"
            variant={danger ? 'danger' : 'primary'}
            onClick={onConfirm}
            autoFocus
          >
            {confirmLabel || tr('确定', 'OK')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
