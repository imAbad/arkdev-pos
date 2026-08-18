import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from audit.services import log_action
from catalog.services import InsufficientStockError, decrement_batch_stock
from customers.services import CreditError, charge_credit
from sales.models import CashShift, Payment, Sale, SaleDetail


class ShiftError(Exception):
    """Error de regla de negocio al abrir/cerrar turno (-> 400)."""


class RegisterAlreadyOpenError(ShiftError):
    """La caja seleccionada ya tiene un turno abierto (de quien sea) — se
    distingue de ShiftError genérico porque el frontend necesita reaccionar
    distinto: en vez de solo mostrar el mensaje, ofrece continuar/cerrar/
    vender en el turno existente (punto 0, bug real reportado: admin
    quedaba varado sin ninguna acción disponible)."""


class ShiftPermissionError(Exception):
    """Quien intenta la acción no tiene autoridad para hacerla (-> 403)."""


class SaleError(Exception):
    """Error de regla de negocio al registrar una venta (-> 400)."""


def compute_expected_totals(shift):
    """Efectivo/voucher que el sistema espera encontrar al cierre, a partir
    de las ventas reales del turno — este era el único lugar que había que
    extender cuando Sale/Payment existieran (ver la nota anterior en este
    mismo archivo, ya resuelta): CREDIT (fiado) no entra a ninguna de las
    dos sumas porque no mueve dinero en la caja al momento de la venta.
    """
    payments = Payment.objects.filter(sale__cash_shift=shift, sale__status=Sale.Status.COMPLETED)

    cash_total = payments.filter(method=Payment.Method.CASH).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    voucher_total = (
        payments.filter(method__in=[Payment.Method.CARD, Payment.Method.TRANSFER])
        .aggregate(total=Sum('amount'))['total']
        or Decimal('0')
    )

    return {
        'cash': shift.opening_balance + cash_total,
        'voucher': voucher_total,
    }


def open_shift(*, user, cash_register, opening_balance=Decimal('0')):
    profile = user.profile

    if cash_register.branch_id != profile.branch_id:
        raise ShiftError('La caja no pertenece a tu sucursal.')
    if not cash_register.is_active:
        raise ShiftError('La caja está inactiva.')
    if CashShift.objects.filter(user=user, status=CashShift.Status.OPEN).exists():
        raise ShiftError('Ya tienes un turno abierto.')
    if CashShift.objects.filter(cash_register=cash_register, status=CashShift.Status.OPEN).exists():
        raise RegisterAlreadyOpenError('Esta caja ya tiene un turno abierto.')

    try:
        with transaction.atomic():
            return CashShift.objects.create(
                cash_register=cash_register,
                user=user,
                opening_balance=opening_balance,
            )
    except IntegrityError:
        # Garantía real contra la condición de carrera: el UniqueConstraint
        # parcial en CashShift.Meta, no el filter() de arriba (que es
        # solo un chequeo "amigable" para dar buen mensaje de error).
        raise RegisterAlreadyOpenError('Esta caja ya tiene un turno abierto.')


def close_shift(*, shift, closing_user, actual_closing_balance, actual_voucher_total=Decimal('0')):
    if shift.status == CashShift.Status.CLOSED:
        raise ShiftError('Este turno ya está cerrado.')

    profile = closing_user.profile
    is_owner = shift.user_id == closing_user.id
    is_admin = profile.role == profile.Role.ADMINISTRADOR
    is_override = profile.can_authorize_exceptions

    if not (is_owner or is_admin or is_override):
        raise ShiftPermissionError('Solo el dueño del turno, un administrador o un supervisor autorizado pueden cerrarlo.')

    expected = compute_expected_totals(shift)

    shift.actual_closing_balance = actual_closing_balance
    shift.actual_voucher_total = actual_voucher_total
    shift.expected_closing_balance = expected['cash']
    shift.expected_voucher_total = expected['voucher']
    shift.closed_at = timezone.now()
    shift.closed_by = closing_user
    shift.status = CashShift.Status.CLOSED
    shift.save()

    if not is_owner:
        log_action(
            company=shift.company,
            user=closing_user,
            action='cash_shift.closed_by_override',
            instance=shift,
            changes={
                'owner': shift.user.email,
                'closed_by': closing_user.email,
                'via': 'ADMINISTRADOR' if is_admin else 'can_authorize_exceptions',
            },
        )

    return shift


def create_sale(
    *, cash_shift, details, payments, occurred_at=None, discount_amount=Decimal('0'),
    client_uuid=None, client=None,
):
    """Registra una venta completa: líneas + pagos divididos, en una sola
    transacción.

    `details`: lista de dicts {'product', 'batch' (opcional), 'quantity',
    'unit_price'} — ya resueltos a instancias de modelo y ya acotados al
    tenant por quien llama (la vista), esta función no vuelve a filtrar por
    tenant, solo aplica reglas de negocio.
    `payments`: lista de dicts {'method', 'amount'} — deben sumar exacto el
    total calculado, si no, la venta se rechaza completa (rollback).
    `client`: obligatorio si algún payment es CREDIT (fiado) — se carga a su
    CreditAccount vía customers.services.charge_credit.
    """
    if cash_shift.status != CashShift.Status.OPEN:
        raise SaleError('No hay un turno abierto para registrar la venta.')
    if not details:
        raise SaleError('La venta necesita al menos una línea.')
    if not payments:
        raise SaleError('La venta necesita al menos un pago.')

    credit_total = sum((p['amount'] for p in payments if p['method'] == Payment.Method.CREDIT), Decimal('0'))
    if credit_total > 0 and client is None:
        raise SaleError('Un pago a crédito necesita un cliente asociado a la venta.')

    occurred_at = occurred_at or timezone.now()
    client_uuid = client_uuid or uuid.uuid4()

    with transaction.atomic():
        subtotal = Decimal('0')
        tax_total = Decimal('0')
        detail_rows = []

        for line in details:
            product = line['product']
            batch = line.get('batch')
            quantity = line['quantity']
            unit_price = line['unit_price']

            if batch is not None and batch.product_id != product.id:
                raise SaleError(f'El lote {batch.batch_number} no corresponde al producto {product.name}.')

            if batch is not None:
                try:
                    decrement_batch_stock(batch=batch, quantity=quantity)
                except InsufficientStockError as exc:
                    raise SaleError(f'No hay suficiente stock de {product.name}. {exc}')

            line_subtotal = quantity * unit_price
            tax_rate_applied = product.tax_rate
            line_tax = (line_subtotal * tax_rate_applied / Decimal('100')).quantize(Decimal('0.01'))

            subtotal += line_subtotal
            tax_total += line_tax
            detail_rows.append({
                'product': product,
                'batch': batch,
                'quantity': quantity,
                'unit_price': unit_price,
                'tax_rate_applied': tax_rate_applied,
                'tax_amount': line_tax,
            })

        total = subtotal - discount_amount + tax_total

        payments_total = sum((p['amount'] for p in payments), Decimal('0'))
        if payments_total != total:
            raise SaleError(f'Los pagos suman {payments_total} pero la venta totaliza {total}.')

        sale = Sale(
            cash_shift=cash_shift,
            client=client,
            client_uuid=client_uuid,
            occurred_at=occurred_at,
            subtotal=subtotal,
            discount_amount=discount_amount,
            tax_amount=tax_total,
            total=total,
        )
        sale.save()

        # .create() uno por uno, no bulk_create: SaleDetail.save()/Payment.save()
        # derivan `company` de `sale` — bulk_create no llama save() por fila.
        for row in detail_rows:
            SaleDetail.objects.create(sale=sale, **row)
        for p in payments:
            Payment.objects.create(
                sale=sale, method=p['method'], amount=p['amount'], reference=p.get('reference', ''),
            )

        if credit_total > 0:
            try:
                charge_credit(account=client.credit_account, amount=credit_total, sale=sale)
            except CreditError as exc:
                # Dentro del atomic: si el crédito no alcanza, TODA la venta
                # se revierte (stock incluido), no solo el cargo.
                raise SaleError(str(exc))

    return sale
