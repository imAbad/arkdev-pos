from django.utils import timezone
from rest_framework import serializers

from catalog.models import Batch, Category, Product, Supplier
from core.serializers import TenantScopedFieldsMixin


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'is_active', 'company']
        read_only_fields = ['slug', 'company']


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'contact_name', 'phone', 'email', 'company']
        read_only_fields = ['company']


class ProductSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    tenant_scoped_fields = ('category', 'supplier')
    nearest_batch_expiration = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'barcode', 'category', 'supplier',
            'unit_type', 'requires_batch', 'variant_attributes',
            'cost_price', 'sale_price', 'tax_rate', 'min_stock', 'image',
            'nearest_batch_expiration', 'company', 'created_at', 'updated_at',
        ]
        read_only_fields = ['company', 'created_at', 'updated_at']

    def get_nearest_batch_expiration(self, product):
        # Punto 4: aviso de caducidad próxima visible en el buscador/
        # carrito de venta — se calcula aquí (no en un endpoint aparte)
        # porque es justo el endpoint que ProductSearch ya usa, sin
        # request extra. Una query por producto es aceptable al tamaño
        # de una lista de búsqueda ya paginada (<=25), no es un export
        # masivo. Tenant-wide, no por sucursal — Batch sí tiene branch
        # pero el buscador de producto no filtra por sucursal todavía.
        nearest = (
            product.batches.filter(current_quantity__gt=0, expiration_date__gte=timezone.localdate())
            .order_by('expiration_date')
            .values_list('expiration_date', flat=True)
            .first()
        )
        return nearest


class BatchSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    tenant_scoped_fields = ('product', 'branch')

    class Meta:
        model = Batch
        fields = [
            'id', 'product', 'branch', 'batch_number', 'initial_quantity',
            'current_quantity', 'expiration_date', 'received_date', 'company',
        ]
        read_only_fields = ['current_quantity', 'received_date', 'company']
