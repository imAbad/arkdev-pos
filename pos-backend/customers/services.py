from customers.models import CreditMovement


class CreditError(Exception):
    """Error de regla de negocio de crédito/fiado (-> 400)."""


def charge_credit(*, account, amount, sale=None):
    """CARGO: aumenta lo que el cliente debe. Valida contra `credit_limit`
    — sin esto el campo sería puramente decorativo. Se llama desde
    `sales.services.create_sale` cuando una venta tiene un `Payment` con
    `method=CREDIT`; también reutilizable para un cargo manual sin venta.
    """
    if account.balance + amount > account.client.credit_limit:
        available = account.client.credit_limit - account.balance
        raise CreditError(
            f'El cargo de {amount} excede el crédito disponible de {account.client.name} '
            f'({available} disponibles de {account.client.credit_limit}).'
        )

    CreditMovement.objects.create(account=account, sale=sale, amount=amount, type=CreditMovement.Type.CARGO)
    account.balance += amount
    account.save(update_fields=['balance'])
    return account


def pay_credit(*, account, amount, sale=None):
    """ABONO: reduce lo que el cliente debe. `sale` casi siempre None — un
    abono normalmente no viene de una venta (ver arquitectura_tecnica_pos.md
    §4.4)."""
    CreditMovement.objects.create(account=account, sale=sale, amount=amount, type=CreditMovement.Type.ABONO)
    account.balance -= amount
    account.save(update_fields=['balance'])
    return account
