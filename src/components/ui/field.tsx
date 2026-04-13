import * as React from "react"

const Field = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`space-y-2 ${className || ""}`}
    {...props}
  />
))
Field.displayName = "Field"

const FieldLabel = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement>
>(({ className, ...props }, ref) => (
  <label
    ref={ref}
    className={`flex items-center text-sm font-medium tracking-widest uppercase text-[#46494C] gap-2 ${className || ""}`}
    {...props}
  />
))
FieldLabel.displayName = "FieldLabel"

export { Field, FieldLabel }
