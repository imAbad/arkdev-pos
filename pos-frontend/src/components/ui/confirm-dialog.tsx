import * as Dialog from '@radix-ui/react-dialog'
import { Button } from '@/components/ui/button'
import { t } from '@/i18n'

interface ConfirmDialogProps {
  open: boolean
  message: string
  confirmLabel: string
  onConfirm: () => void
  onOpenChange: (open: boolean) => void
}

/** Confirmación para acciones destructivas (ej. cancelar venta) — un
 * diálogo chico está bien aquí, a diferencia de la confirmación de venta
 * completada, que sí debe ser una pantalla grande (ver SaleConfirmation). */
export function ConfirmDialog({ open, message, confirmLabel, onConfirm, onOpenChange }: ConfirmDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-[90vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-3xl bg-white p-8 shadow-lg">
          <Dialog.Title className="text-2xl font-semibold text-ink">{message}</Dialog.Title>
          <div className="mt-8 flex gap-4">
            <Button variant="neutral" size="compact" className="flex-1" onClick={() => onOpenChange(false)}>
              {t.common.no}
            </Button>
            <Button
              variant="cancel"
              size="compact"
              className="flex-1"
              onClick={() => {
                onConfirm()
                onOpenChange(false)
              }}
            >
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
