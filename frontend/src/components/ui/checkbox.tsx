import * as React from 'react'
import { cn } from '../../utils/cn'
import './ui.css'

type CheckboxProps = Omit<React.ComponentPropsWithoutRef<'input'>, 'type'>

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      type="checkbox"
      className={cn('ui-checkbox', className)}
      {...props}
    />
  ),
)
Checkbox.displayName = 'Checkbox'

export { Checkbox }
export type { CheckboxProps }
