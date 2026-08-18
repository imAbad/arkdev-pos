from sales.models import CashRegister


def create_cash_register(branch, name='Caja 1', is_active=True):
    return CashRegister.objects.create(branch=branch, name=name, is_active=is_active)
