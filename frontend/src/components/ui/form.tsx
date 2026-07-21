import * as React from 'react'
import { cn } from '../../utils/cn'
import './ui.css'

type AriaInvalid = React.AriaAttributes['aria-invalid']

interface FieldContextValue {
  controlId: string
  descriptionId?: string
  messageId?: string
  invalid: boolean
}

const FieldContext = React.createContext<FieldContextValue | null>(null)

interface FieldProps extends React.ComponentPropsWithoutRef<'div'> {
  controlId?: string
  description?: React.ReactNode
  error?: React.ReactNode
  htmlFor?: string
  invalid?: boolean
  label?: React.ReactNode
  required?: boolean
}

interface FormControlStateProps {
  invalid?: boolean
}

type InputProps = React.ComponentPropsWithoutRef<'input'> & FormControlStateProps
type TextareaProps = React.ComponentPropsWithoutRef<'textarea'> & FormControlStateProps
type SelectProps = React.ComponentPropsWithoutRef<'select'> & FormControlStateProps

function hasContent(value: React.ReactNode): boolean {
  return value !== undefined && value !== null && value !== false && value !== ''
}

function joinIds(...ids: Array<string | undefined>): string | undefined {
  const value = ids.filter(Boolean).join(' ')
  return value || undefined
}

function resolveInvalidState(
  invalid: boolean | undefined,
  ariaInvalid: AriaInvalid,
  fieldInvalid: boolean | undefined,
): AriaInvalid {
  if (invalid !== undefined) {
    return invalid || undefined
  }

  if (ariaInvalid !== undefined) {
    return ariaInvalid
  }

  return fieldInvalid || undefined
}

function isInvalidState(value: AriaInvalid): boolean {
  return value !== undefined && value !== false && value !== 'false'
}

function useFieldControl({
  ariaDescribedBy,
  ariaInvalid,
  id,
  invalid,
}: {
  ariaDescribedBy?: string
  ariaInvalid: AriaInvalid
  id?: string
  invalid?: boolean
}) {
  const field = React.useContext(FieldContext)
  const invalidState = resolveInvalidState(invalid, ariaInvalid, field?.invalid)

  return {
    controlId: id ?? field?.controlId,
    describedBy: joinIds(
      ariaDescribedBy,
      field?.descriptionId,
      isInvalidState(invalidState) ? field?.messageId : undefined,
    ),
    invalidState,
  }
}

const Field = React.forwardRef<HTMLDivElement, FieldProps>(
  (
    {
      children,
      className,
      controlId,
      description,
      error,
      htmlFor,
      invalid,
      label,
      required,
      ...props
    },
    ref,
  ) => {
    const generatedId = React.useId()
    const resolvedControlId = controlId ?? htmlFor ?? `ui-form-${generatedId}`
    const hasDescription = hasContent(description)
    const hasError = hasContent(error)
    const fieldInvalid = invalid ?? hasError
    const descriptionId = hasDescription ? `${resolvedControlId}-description` : undefined
    const messageId = hasError ? `${resolvedControlId}-message` : undefined

    const contextValue = React.useMemo<FieldContextValue>(
      () => ({
        controlId: resolvedControlId,
        descriptionId,
        invalid: fieldInvalid,
        messageId,
      }),
      [descriptionId, fieldInvalid, messageId, resolvedControlId],
    )

    return (
      <FieldContext.Provider value={contextValue}>
        <div
          ref={ref}
          className={cn('ui-form-field', className)}
          data-invalid={fieldInvalid ? 'true' : undefined}
          {...props}
        >
          {hasContent(label) ? (
            <label className="ui-form-label" htmlFor={htmlFor ?? resolvedControlId}>
              <span>{label}</span>
              {required ? (
                <span aria-hidden="true" className="ui-form-required">
                  *
                </span>
              ) : null}
            </label>
          ) : null}
          {children}
          {hasDescription ? (
            <p className="ui-form-description" id={descriptionId}>
              {description}
            </p>
          ) : null}
          {hasError ? (
            <p className="ui-form-message" id={messageId} role="alert">
              {error}
            </p>
          ) : null}
        </div>
      </FieldContext.Provider>
    )
  },
)
Field.displayName = 'Field'

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, id, invalid, 'aria-describedby': ariaDescribedBy, 'aria-invalid': ariaInvalid, ...props }, ref) => {
    const fieldControl = useFieldControl({ ariaDescribedBy, ariaInvalid, id, invalid })

    return (
      <input
        ref={ref}
        id={fieldControl.controlId}
        className={cn('ui-form-control', 'ui-form-input', className)}
        aria-describedby={fieldControl.describedBy}
        aria-invalid={fieldControl.invalidState}
        {...props}
      />
    )
  },
)
Input.displayName = 'Input'

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, id, invalid, 'aria-describedby': ariaDescribedBy, 'aria-invalid': ariaInvalid, ...props }, ref) => {
    const fieldControl = useFieldControl({ ariaDescribedBy, ariaInvalid, id, invalid })

    return (
      <textarea
        ref={ref}
        id={fieldControl.controlId}
        className={cn('ui-form-control', 'ui-form-textarea', className)}
        aria-describedby={fieldControl.describedBy}
        aria-invalid={fieldControl.invalidState}
        {...props}
      />
    )
  },
)
Textarea.displayName = 'Textarea'

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, id, invalid, 'aria-describedby': ariaDescribedBy, 'aria-invalid': ariaInvalid, ...props }, ref) => {
    const fieldControl = useFieldControl({ ariaDescribedBy, ariaInvalid, id, invalid })

    return (
      <select
        ref={ref}
        id={fieldControl.controlId}
        className={cn('ui-form-control', 'ui-form-select', className)}
        aria-describedby={fieldControl.describedBy}
        aria-invalid={fieldControl.invalidState}
        {...props}
      />
    )
  },
)
Select.displayName = 'Select'

export { Field, Input, Select, Textarea }
export type { FieldProps, InputProps, SelectProps, TextareaProps }
