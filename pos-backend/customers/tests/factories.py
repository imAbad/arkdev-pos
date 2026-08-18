from decimal import Decimal

from customers.models import Client


def create_client(company, name='Cliente Fiel', phone='', credit_limit=Decimal('500.00')):
    return Client.objects.create(company=company, name=name, phone=phone, credit_limit=credit_limit)
