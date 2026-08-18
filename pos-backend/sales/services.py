from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.services import log_action
from sales.models import CashShift


class ShiftError(Exception):
    """Error de regla de negocio al abrir/cerrar turno (-> 400)."""


class ShiftPermissionError(Exception):
    """Quien intenta la acción no tiene autoridad para hacerla (-> 403)."""


def compute_expected_totals(shift):
    """Efectivo/voucher que el sistema espera encontrar al cierre.

    Hoy solo cuenta el fondo de apertura: `sales.Sale`/`Payment` todavía no
    existen (construcción pendiente en el punto 4 del orden de construcción,
    ver arquitectura_tecnica_pos.md §9). Cuando existan, este es el único
    lugar que hay que extender para sumarlas por método de pago — el resto
    de open_shift/close_shift no cambia.
    """
    return {
        'cash': shift.opening_balance,
        'voucher': Decimal('0'),
    }


def open_shift(*, user, cash_register, opening_balance=Decimal('0')):
    profile = user.profile

    if cash_register.branch_id != profile.branch_id:
        raise ShiftError('La caja no pertenece a tu sucursal.')
    if not cash_register.is_active:
        raise ShiftError('La caja está inactiva.')
    if CashShift.objects.filter(user=user, status=CashShift.Status.OPEN).exists():
        raise ShiftError('Ya tienes un turno abierto.')

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
        raise ShiftError('Esta caja ya tiene un turno abierto.')


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
