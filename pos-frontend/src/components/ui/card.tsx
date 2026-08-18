import * as React from 'react'
import { cn } from '@/lib/utils'

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('rounded-3xl border-2 border-border bg-white p-8 shadow-sm', className)}
      {...props}
    />
  )
}
