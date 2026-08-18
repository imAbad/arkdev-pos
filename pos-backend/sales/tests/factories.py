from decimal import Decimal

from sales.models import CashRegister
from sales.services import create_sale, open_shift


def create_cash_register(branch, name='Caja 1', is_active=True):
    return CashRegister.objects.create(branch=branch, name=name, is_active=is_active)


def create_checkout_context(
    company_name='Abarrotes Don Chuy', branch_name='Centro', user_email='cajero@donchuy.test',
    tax_rate=Decimal('16'),
):
    """Arma todo lo necesario para poder registrar una venta: tenant
    completo con capability handles_cash, caja, turno abierto y un
    producto — evita repetir este setup en cada test de sales."""
    from catalog.tests.factories import create_product
    from tenants.tests.factories import create_full_tenant

    tenant = create_full_tenant(company_name, branch_name, user_email, capabilities={'handles_cash': True})
    register = create_cash_register(tenant['branch'])
    shift = open_shift(user=tenant['user'], cash_register=register)
    product = create_product(tenant['company'], tax_rate=tax_rate)
    return {**tenant, 'register': register, 'shift': shift, 'product': product}


def make_sale(
    cash_shift,
    product,
    batch=None,
    quantity=Decimal('1'),
    unit_price=Decimal('10.00'),
    payment_method='CASH',
    discount_amount=Decimal('0'),
    client_uuid=None,
    client=None,
):
    """Atajo de una línea + un pago por el total exacto — el caso más común
    en los tests de sales."""
    line_subtotal = quantity * unit_price
    tax_amount = (line_subtotal * product.tax_rate / Decimal('100')).quantize(Decimal('0.01'))
    total = line_subtotal - discount_amount + tax_amount

    return create_sale(
        cash_shift=cash_shift,
        client=client,
        details=[{'product': product, 'batch': batch, 'quantity': quantity, 'unit_price': unit_price}],
        payments=[{'method': payment_method, 'amount': total}],
        discount_amount=discount_amount,
        client_uuid=client_uuid,
    )
