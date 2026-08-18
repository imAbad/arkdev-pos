import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

// Botones grandes y táctiles por default (mín. 56px de alto) — personal
// con poca práctica en pantallas táctiles necesita objetivos grandes, no
// el tamaño compacto que trae shadcn por default. Solo 3 variantes de
// color con significado fijo: confirm (verde), cancel (rojo), neutral
// (gris, para navegación/secundarias — nunca azul, ver index.css).
const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-2xl font-semibold ' +
    'transition-colors disabled:opacity-40 disabled:pointer-events-none ' +
    'focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-2',
  {
    variants: {
      variant: {
        confirm: 'bg-confirm text-white hover:bg-confirm-hover focus-visible:outline-confirm',
        cancel: 'bg-cancel text-white hover:bg-cancel-hover focus-visible:outline-cancel',
        neutral:
          'bg-white text-ink border-2 border-border hover:bg-surface-muted focus-visible:outline-ink',
      },
      size: {
        default: 'h-16 px-6 text-xl',
        large: 'h-20 px-8 text-2xl',
        compact: 'h-12 px-4 text-base',
      },
    },
    defaultVariants: {
      variant: 'neutral',
      size: 'default',
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  },
)
Button.displayName = 'Button'
