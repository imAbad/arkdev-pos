from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from catalog.models import Batch, Category, Product, Supplier


def create_category(company, name='General'):
    return Category.objects.create(company=company, name=name)


def create_supplier(company, name='Proveedor Genérico'):
    return Supplier.objects.create(company=company, name=name)


def create_product(company, category=None, supplier=None, name='Producto', sku='SKU-1', **kwargs):
    if category is None:
        # get_or_create, no create: varias llamadas sin category explícita
        # para la misma company deben compartir la "General" por default,
        # no chocar contra el unique_together (company, name).
        category, _ = Category.objects.get_or_create(company=company, name='General')
    fields = {
        'name': name,
        'sku': sku,
        'category': category,
        'supplier': supplier,
        'cost_price': Decimal('10.00'),
        'sale_price': Decimal('15.00'),
    }
    fields.update(kwargs)
    return Product.objects.create(company=company, **fields)


def create_batch(product, branch, batch_number='L-1', initial_quantity=10, expiration_date=None):
    expiration_date = expiration_date or (timezone.localdate() + timedelta(days=30))
    return Batch.objects.create(
        product=product,
        branch=branch,
        batch_number=batch_number,
        initial_quantity=initial_quantity,
        expiration_date=expiration_date,
    )
