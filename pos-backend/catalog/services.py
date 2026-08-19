from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from catalog.models import Batch, InventoryAdjustment, Product


class InsufficientStockError(Exception):
    """Stock insuficiente en el lote para completar la operación (-> 400)."""


class InventoryAdjustmentError(Exception):
    """Error de regla de negocio al ajustar stock manualmente (-> 400)."""


def adjust_batch_stock(*, batch, quantity_delta, reason, actor, reason_detail=''):
    """Único camino auditado para cambiar Batch.current_quantity fuera de
    una venta — BatchSerializer deja current_quantity de solo lectura a
    propósito (observación de sesión, ronda de 4 piezas, punto 4: no
    había NINGUNA forma de ajustar stock manualmente ni de dejar
    constancia de por qué, ver el docstring completo de
    catalog.models.InventoryAdjustment).

    Motivo obligatorio desde aquí, no solo desde el frontend: 'OTHER' sin
    `reason_detail` se rechaza — un motivo "Otro" sin texto no dice nada
    útil en un reporte de mermas, sería tan inservible como no tener
    motivo en absoluto.
    """
    if quantity_delta == 0:
        raise InventoryAdjustmentError('El ajuste no puede ser de 0 — captura la diferencia real.')
    if reason == InventoryAdjustment.Reason.OTHER and not reason_detail.strip():
        raise InventoryAdjustmentError('Si el motivo es "Otro", describe brevemente la razón.')

    with transaction.atomic():
        locked_batch = Batch.objects.select_for_update().get(pk=batch.pk)
        quantity_before = locked_batch.current_quantity
        quantity_after = quantity_before + quantity_delta
        if quantity_after < 0:
            raise InventoryAdjustmentError(
                f'El ajuste dejaría el lote {locked_batch.batch_number} en {quantity_after} — '
                f'no puede quedar en negativo ({quantity_before} disponibles).'
            )

        locked_batch.current_quantity = quantity_after
        locked_batch.save(update_fields=['current_quantity'])

        adjustment = InventoryAdjustment.objects.create(
            batch=locked_batch, user=actor, quantity_delta=quantity_delta,
            quantity_before=quantity_before, quantity_after=quantity_after,
            reason=reason, reason_detail=reason_detail,
        )
    return adjustment


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


def low_stock_products(*, company):
    """Punto 7: reorder point simplificado — compara stock real contra
    Product.min_stock directo. La fórmula completa (venta promedio diaria
    x lead time + stock de seguridad) queda para más adelante, cuando haya
    historial de ventas suficiente para calcularla; usar min_stock tal
    cual es decisión ya tomada para esta ronda, no se reabre aquí.

    Limitación real y deliberada, no silenciosa: solo aplica a productos
    con requires_batch=True. Son los únicos con una cantidad de stock
    real rastreada (Batch.current_quantity) — el resto del catálogo no
    tiene ningún mecanismo de conteo de existencias en el modelo actual
    (mismo hallazgo que ya limita expired_stock_report/near_expiry, punto
    1 y 4 de esta sesión). No se puede calcular "stock bajo" contra un
    número que el sistema no mide todavía.

    Solo cuenta stock vigente (no vencido) hacia el total: un lote
    caducado no es stock vendible, así que ignorarlo evita que un
    producto con mucho stock caduco parezca bien abastecido cuando en
    realidad necesita reposición — mismo criterio de "disponible" que ya
    usa decrement_stock_fefo.
    """
    today = timezone.localdate()
    products = Product.objects.filter(company=company, requires_batch=True).order_by('name')

    rows = []
    for product in products:
        current_stock = (
            Batch.objects.filter(product=product, expiration_date__gte=today)
            .aggregate(total=Sum('current_quantity'))['total']
            or 0
        )
        if current_stock <= product.min_stock:
            rows.append({
                'product_id': product.id,
                'product_name': product.name,
                'sku': product.sku,
                'current_stock': current_stock,
                'min_stock': product.min_stock,
            })
    return rows
