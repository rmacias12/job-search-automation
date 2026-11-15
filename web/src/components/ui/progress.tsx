import * as React from "react"

import { cn } from "@/lib/utils"

const Progress = React.forwardRef<
  HTMLProgressElement,
  React.ProgressHTMLAttributes<HTMLProgressElement>
>(({ className, value, ...props }, ref) => (
  <progress
    ref={ref}
    className={cn(
      "h-2 w-full overflow-hidden rounded-full bg-primary/20",
      className
    )}
    value={value}
    {...props}
  />
))
Progress.displayName = "Progress"

export { Progress }