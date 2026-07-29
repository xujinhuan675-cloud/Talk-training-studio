import * as React from 'react'
import { cn } from '../../utils/cn'
import './ui.css'

type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'accent' | 'violet'

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone
}

function Badge({ tone = 'neutral', className, ...props }: BadgeProps) {
  return <span className={cn('ui-badge', `ui-badge--${tone}`, className)} {...props} />
}

export { Badge }
export type { BadgeProps, BadgeTone }
