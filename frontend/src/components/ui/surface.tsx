import * as React from 'react'
import { cn } from '../../utils/cn'
import './ui.css'

type SurfaceVariant = 'plain' | 'raised' | 'accent'
type SurfacePadding = 'none' | 'sm' | 'md' | 'lg'

interface SurfaceProps extends React.HTMLAttributes<HTMLElement> {
  as?: 'article' | 'section' | 'div'
  variant?: SurfaceVariant
  padding?: SurfacePadding
}

function Surface({
  as: Component = 'section',
  variant = 'plain',
  padding = 'md',
  className,
  ...props
}: SurfaceProps) {
  return (
    <Component
      className={cn('ui-surface', `ui-surface--${variant}`, `ui-surface--padding-${padding}`, className)}
      {...props}
    />
  )
}

export { Surface }
