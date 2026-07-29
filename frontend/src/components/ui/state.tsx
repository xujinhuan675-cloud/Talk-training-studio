import * as React from 'react'
import { cn } from '../../utils/cn'
import './ui.css'

type StateBlockTone = 'neutral' | 'loading' | 'success' | 'warning' | 'danger' | 'accent'
type StateBlockSize = 'sm' | 'md' | 'lg'

interface StateBlockProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  actions?: React.ReactNode
  description?: React.ReactNode
  icon?: React.ReactNode
  size?: StateBlockSize
  title?: React.ReactNode
  tone?: StateBlockTone
}

function StateBlock({
  actions,
  className,
  description,
  icon,
  size = 'md',
  title,
  tone = 'neutral',
  ...props
}: StateBlockProps) {
  return (
    <div className={cn('ui-state-block', `ui-state-block--${tone}`, `ui-state-block--${size}`, className)} {...props}>
      {icon ? <div className="ui-state-icon">{icon}</div> : null}
      {title ? <h2>{title}</h2> : null}
      {description ? <p>{description}</p> : null}
      {actions ? <div className="ui-state-actions">{actions}</div> : null}
    </div>
  )
}

function StateSpinner(props: React.HTMLAttributes<HTMLSpanElement>) {
  const { className, ...rest } = props
  return <span aria-hidden="true" className={cn('ui-state-spinner', className)} {...rest} />
}

export { StateBlock, StateSpinner }
export type { StateBlockProps, StateBlockSize, StateBlockTone }
