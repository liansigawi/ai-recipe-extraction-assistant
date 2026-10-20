interface FieldErrorProps {
  id: string
  message: string | undefined
}

// The error message under a form field. The field points at it with aria-describedby={id},
// so a screen reader reads the message together with the field.
export default function FieldError({ id, message }: FieldErrorProps) {
  if (message === undefined) return null
  return (
    <p id={id} className="field-error">
      {message}
    </p>
  )
}
