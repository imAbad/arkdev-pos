import * as React from 'react'
import { cn } from '@/lib/utils'

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-16 w-full rounded-2xl border-2 border-border bg-white px-5 text-xl text-ink',
        'placeholder:text-ink/40',
        'focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-2 focus-visible:outline-accent',
        'disabled:opacity-40',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'
