import { jsx as _jsx } from "react/jsx-runtime";
import * as React from "react";
const Field = React.forwardRef(({ className, ...props }, ref) => (_jsx("div", { ref: ref, className: `space-y-2 ${className || ""}`, ...props })));
Field.displayName = "Field";
const FieldLabel = React.forwardRef(({ className, ...props }, ref) => (_jsx("label", { ref: ref, className: `flex items-center text-sm font-medium tracking-widest uppercase text-[#46494C] gap-2 ${className || ""}`, ...props })));
FieldLabel.displayName = "FieldLabel";
export { Field, FieldLabel };
