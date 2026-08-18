from catalog.models import Batch


class InsufficientStockError(Exception):
    """Stock insuficiente en el lote para completar la operación (-> 400)."""


def decrement_batch_stock(*, batch, quantity):
    """Descuenta stock de un lote de forma segura ante concurrencia real
    (select_for_update, mismo patrón que sales.services para CashShift).

    No hace selección FEFO automática — el lote ya viene elegido por quien
    llama (ver sales.services.create_sale). Auto-selección FEFO es una
    posible mejora futura, no pedida todavía.
    """
    locked_batch = Batch.objects.select_for_update().get(pk=batch.pk)
    if locked_batch.current_quantity < quantity:
        raise InsufficientStockError(
            f'Stock insuficiente en el lote {locked_batch.batch_number} '
            f'({locked_batch.current_quantity} disponibles, se pidieron {quantity}).'
        )
    locked_batch.current_quantity -= quantity
    locked_batch.save(update_fields=['current_quantity'])
    return locked_batch
