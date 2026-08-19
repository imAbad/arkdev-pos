from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from catalog.models import Batch, Category, InventoryAdjustment, Product, Supplier
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


class RelatedProductSummarySerializer(serializers.ModelSerializer):
    """Solo lo que la sugerencia de cross-sell en la pantalla de venta
    necesita mostrar — no el Product completo (evita anidar costo/margen,
    dato que un cajero no necesita ver ahí)."""

    class Meta:
        model = Product
        fields = ['id', 'name', 'sale_price']


class ProductSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    tenant_scoped_fields = ('category', 'supplier')
    nearest_batch_expiration = serializers.SerializerMethodField()
    current_stock = serializers.SerializerMethodField()
    related_products_detail = RelatedProductSummarySerializer(source='related_products', many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'barcode', 'category', 'supplier',
            'unit_type', 'requires_batch', 'variant_attributes',
            'cost_price', 'sale_price', 'tax_rate', 'min_stock', 'image',
            'nearest_batch_expiration', 'current_stock', 'related_products', 'related_products_detail',
            'company', 'created_at', 'updated_at',
        ]
        read_only_fields = ['company', 'created_at', 'updated_at']

    def validate_related_products(self, products):
        # TenantScopedFieldsMixin no acota M2M (solo FK simples vía
        # PrimaryKeyRelatedField.queryset) — se valida aquí explícito,
        # mismo motivo que cualquier otro campo cruzado a otro tenant.
        request = self.context.get('request')
        if request is not None:
            allowed_ids = set(Product.objects.for_user(request.user).values_list('id', flat=True))
            for product in products:
                if product.id not in allowed_ids:
                    raise serializers.ValidationError('No puedes relacionar un producto de otro tenant.')
        if self.instance is not None and any(product.id == self.instance.id for product in products):
            raise serializers.ValidationError('Un producto no puede relacionarse consigo mismo.')
        return products

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

    def get_current_stock(self, product):
        # Observación de sesión (ronda de 4 piezas, punto 1): sin esto,
        # la pantalla de Inventario solo mostraba stock abriendo "Lotes"
        # producto por producto — inutilizable para un vistazo rápido.
        # `None` (no 0) cuando requires_batch=False es deliberado, no un
        # descuido: ese caso no tiene NINGÚN mecanismo de conteo de
        # existencias en el modelo actual (mismo hallazgo ya documentado
        # en catalog.services.low_stock_products) — 0 insinuaría "sin
        # existencias" cuando en realidad es "no rastreado".
        if not product.requires_batch:
            return None
        qs = product.batches.filter(current_quantity__gt=0, expiration_date__gte=timezone.localdate())
        request = self.context.get('request')
        branch_id = request.query_params.get('branch') if request is not None else None
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs.aggregate(total=Sum('current_quantity'))['total'] or 0


class BatchSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    tenant_scoped_fields = ('product', 'branch')

    class Meta:
        model = Batch
        fields = [
            'id', 'product', 'branch', 'batch_number', 'initial_quantity',
            'current_quantity', 'expiration_date', 'received_date', 'company',
        ]
        read_only_fields = ['current_quantity', 'received_date', 'company']


class InventoryAdjustmentInputSerializer(serializers.Serializer):
    """Input de BatchViewSet.adjust — motivo obligatorio, `reason_detail`
    solo se exige de verdad si reason='OTHER' (validado en
    catalog.services.adjust_batch_stock, no aquí)."""

    quantity_delta = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=InventoryAdjustment.Reason.choices)
    reason_detail = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class InventoryAdjustmentSerializer(serializers.ModelSerializer):
    reason_label = serializers.CharField(source='get_reason_display', read_only=True)
    product_name = serializers.CharField(source='batch.product.name', read_only=True)
    batch_number = serializers.CharField(source='batch.batch_number', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = InventoryAdjustment
        fields = [
            'id', 'batch', 'product_name', 'batch_number', 'quantity_delta', 'quantity_before',
            'quantity_after', 'reason', 'reason_label', 'reason_detail', 'user_email', 'created_at', 'company',
        ]
        read_only_fields = fields
