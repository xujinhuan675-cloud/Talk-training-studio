import * as React from 'react'
import { cn } from '../../utils/cn'
import './ui.css'

interface SegmentedControlOption<Value extends string> {
  ariaLabel?: string
  disabled?: boolean
  label: React.ReactNode
  title?: string
  value: Value
}

interface SegmentedControlProps<Value extends string>
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange'> {
  ariaLabel: string
  label?: React.ReactNode
  onValueChange: (value: Value) => void
  options: readonly SegmentedControlOption<Value>[]
  size?: 'sm' | 'md'
  value: Value
}

function SegmentedControl<Value extends string>({
  ariaLabel,
  className,
  label,
  onValueChange,
  options,
  size = 'md',
  value,
  ...props
}: SegmentedControlProps<Value>) {
  return (
    <div
      className={cn('ui-segmented-control', `ui-segmented-control--${size}`, className)}
      role="group"
      aria-label={ariaLabel}
      {...props}
    >
      {label ? <span className="ui-segmented-control-label">{label}</span> : null}
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            className="ui-segmented-control-button"
            aria-label={option.ariaLabel}
            aria-pressed={selected}
            data-state={selected ? 'on' : 'off'}
            disabled={option.disabled}
            title={option.title}
            onClick={() => onValueChange(option.value)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export { SegmentedControl }
export type { SegmentedControlOption, SegmentedControlProps }
