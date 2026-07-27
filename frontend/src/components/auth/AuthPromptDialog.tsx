import React from 'react'
import { X } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { useI18n } from '../../i18n'
import { Button } from '../ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogTitle,
} from '../ui/dialog'
import CredentialLoginPanel from './CredentialLoginPanel'
import './AuthPromptDialog.css'

export default function AuthPromptDialog() {
  const { currentUser, closeSignInPrompt, isSignInPromptOpen } = useAuthContext()
  const { tr } = useI18n()
  const open = isSignInPromptOpen && !currentUser

  React.useEffect(() => {
    if (currentUser) closeSignInPrompt()
  }, [closeSignInPrompt, currentUser])

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) closeSignInPrompt()
      }}
    >
      <DialogContent className="auth-prompt-dialog" aria-describedby={undefined}>
        <DialogTitle className="auth-prompt-title">{tr('登录', 'Sign in')}</DialogTitle>
        <DialogClose asChild>
          <Button
            className="auth-prompt-close"
            type="button"
            variant="ghost"
            size="icon"
            aria-label={tr('关闭', 'Close')}
            title={tr('关闭', 'Close')}
          >
            <X size={18} aria-hidden="true" />
          </Button>
        </DialogClose>
        <CredentialLoginPanel
          className="login-panel--prompt"
          headingId="auth-prompt-heading"
          onAuthenticated={closeSignInPrompt}
        />
      </DialogContent>
    </Dialog>
  )
}
