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

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'barcode', 'category', 'supplier',
            'unit_type', 'requires_batch', 'variant_attributes',
            'cost_price', 'sale_price', 'tax_rate', 'min_stock', 'image',
            'company', 'created_at', 'updated_at',
        ]
        read_only_fields = ['company', 'created_at', 'updated_at']


class BatchSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    tenant_scoped_fields = ('product', 'branch')

    class Meta:
        model = Batch
        fields = [
            'id', 'product', 'branch', 'batch_number', 'initial_quantity',
            'current_quantity', 'expiration_date', 'received_date', 'company',
        ]
        read_only_fields = ['current_quantity', 'received_date', 'company']
