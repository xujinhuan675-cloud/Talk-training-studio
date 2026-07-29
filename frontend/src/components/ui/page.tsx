import * as React from 'react'
import { cn } from '../../utils/cn'
import './ui.css'

type PageWidth = 'default' | 'wide' | 'full'

interface PageShellProps extends React.HTMLAttributes<HTMLDivElement> {
  width?: PageWidth
}

interface PageHeaderProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  eyebrow?: React.ReactNode
  icon?: React.ReactNode
  leading?: React.ReactNode
  title: React.ReactNode
  description?: React.ReactNode
  meta?: React.ReactNode
  actions?: React.ReactNode
  stats?: React.ReactNode
}

interface PageSectionProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title?: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
}

interface PageStat {
  label: React.ReactNode
  value: React.ReactNode
  detail?: React.ReactNode
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'accent'
}

interface PageStatGridProps extends React.HTMLAttributes<HTMLDivElement> {
  stats: PageStat[]
}

function PageShell({ width = 'default', className, ...props }: PageShellProps) {
  return <div className={cn('ui-page-shell', `ui-page-shell--${width}`, className)} {...props} />
}

function PageHeader({
  eyebrow,
  icon,
  leading,
  title,
  description,
  meta,
  actions,
  stats,
  className,
  ...props
}: PageHeaderProps) {
  return (
    <header
      className={cn('ui-page-header', stats ? 'ui-page-header--with-stats' : undefined, className)}
      {...props}
    >
      <div className="ui-page-header-main">
        {eyebrow ? (
          <div className="ui-page-eyebrow">
            {icon}
            <span>{eyebrow}</span>
          </div>
        ) : null}
        <div className="ui-page-title-row">
          <div className="ui-page-title-main">
            {leading ? <div className="ui-page-leading">{leading}</div> : null}
            <div className="ui-page-title-copy">
              <h1>{title}</h1>
              {description ? <p>{description}</p> : null}
              {meta ? <div className="ui-page-meta">{meta}</div> : null}
            </div>
          </div>
          {actions ? <div className="ui-page-actions">{actions}</div> : null}
        </div>
      </div>
      {stats ? <div className="ui-page-header-stats">{stats}</div> : null}
    </header>
  )
}

function PageSection({ title, description, actions, className, children, ...props }: PageSectionProps) {
  return (
    <section className={cn('ui-page-section', className)} {...props}>
      {(title || description || actions) ? (
        <div className="ui-page-section-head">
          <div>
            {title ? <h2>{title}</h2> : null}
            {description ? <p>{description}</p> : null}
          </div>
          {actions ? <div className="ui-page-section-actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  )
}

function PageStatGrid({ stats, className, ...props }: PageStatGridProps) {
  return (
    <div className={cn('ui-page-stat-grid', className)} {...props}>
      {stats.map((stat, index) => (
        <div className={cn('ui-page-stat', stat.tone && `ui-page-stat--${stat.tone}`)} key={index}>
          <span>{stat.label}</span>
          <strong>{stat.value}</strong>
          {stat.detail ? <em>{stat.detail}</em> : null}
        </div>
      ))}
    </div>
  )
}

export { PageHeader, PageSection, PageShell, PageStatGrid }
export type { PageStat }
