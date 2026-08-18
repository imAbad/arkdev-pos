from django.utils import timezone

from catalog.models import Batch


class InsufficientStockError(Exception):
    """Stock insuficiente en el lote para completar la operación (-> 400)."""


def decrement_batch_stock(*, batch, quantity):
    """Descuenta stock de UN lote específico ya elegido por quien llama —
    de forma segura ante concurrencia real (select_for_update, mismo
    patrón que sales.services para CashShift). Para ventas normales de un
    producto con requires_batch=True, usar decrement_stock_fefo en vez de
    esta directo: aquí no hay ninguna selección de orden, decrementa
    exactamente el lote que se le pasa."""
    locked_batch = Batch.objects.select_for_update().get(pk=batch.pk)
    if locked_batch.current_quantity < quantity:
        raise InsufficientStockError(
            f'Stock insuficiente en el lote {locked_batch.batch_number} '
            f'({locked_batch.current_quantity} disponibles, se pidieron {quantity}).'
        )
    locked_batch.current_quantity -= quantity
    locked_batch.save(update_fields=['current_quantity'])
    return locked_batch


def decrement_stock_fefo(*, product, branch, quantity):
    """FEFO real (First-Expired-First-Out): entre los lotes con stock
    disponible y no caducados de este producto/sucursal, descuenta del que
    caduca más próximo primero — `order_by('expiration_date')` ascendente
    es la garantía, no una convención de nombres. select_for_update()
    bloquea las filas candidatas hasta el commit, mismo patrón anti-carrera
    que decrement_batch_stock/CashShift.

    No parte una línea de venta entre dos lotes: toma el primer lote (en
    orden de caducidad) que por sí solo alcance a cubrir `quantity`. Si
    ningún lote individual alcanza —aunque la suma de varios sí— se
    rechaza como stock insuficiente; dividir una línea entre lotes
    agregaría complejidad (más de un lote por SaleDetail) no pedida
    todavía.
    """
    candidates = (
        Batch.objects.select_for_update()
        .filter(product=product, branch=branch, current_quantity__gt=0, expiration_date__gte=timezone.localdate())
        .order_by('expiration_date')
    )
    for candidate in candidates:
        if candidate.current_quantity >= quantity:
            candidate.current_quantity -= quantity
            candidate.save(update_fields=['current_quantity'])
            return candidate

    raise InsufficientStockError(
        f'Ningún lote vigente de {product.name} tiene suficiente stock para cubrir {quantity}.'
    )
