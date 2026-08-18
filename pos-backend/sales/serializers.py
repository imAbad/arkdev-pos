from decimal import Decimal

from rest_framework import serializers

from core.serializers import TenantScopedFieldsMixin
from customers.models import Client
from sales.models import CashRegister, CashShift, Payment, Sale, SaleDetail


class CashRegisterSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    # `branch` cruza hacia otro modelo con su propio scoping — sin acotarlo,
    # un usuario podría pasar el id de una branch de OTRO tenant y la
    # company de la caja terminaría derivándose de esa branch ajena
    # (CashRegister.save() deriva company de branch.company).
    tenant_scoped_fields = ('branch',)

    class Meta:
        model = CashRegister
        fields = ['id', 'branch', 'name', 'is_active', 'company', 'created_at', 'updated_at']
        read_only_fields = ['company', 'created_at', 'updated_at']


class CashShiftSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    closed_by_email = serializers.EmailField(source='closed_by.email', read_only=True, default=None)
    cash_difference = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    voucher_difference = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CashShift
        fields = [
            'id', 'cash_register', 'user', 'user_email', 'closed_by', 'closed_by_email',
            'opened_at', 'closed_at', 'opening_balance',
            'expected_closing_balance', 'actual_closing_balance', 'cash_difference',
            'expected_voucher_total', 'actual_voucher_total', 'voucher_difference',
            'status', 'company',
        ]
        read_only_fields = fields


class OpenShiftInputSerializer(serializers.Serializer):
    cash_register_id = serializers.IntegerField()
    opening_balance = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0'))


class CloseShiftInputSerializer(serializers.Serializer):
    actual_closing_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    actual_voucher_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0'))


class SaleDetailSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = SaleDetail
        fields = ['id', 'product', 'batch', 'quantity', 'unit_price', 'tax_rate_applied', 'tax_amount', 'subtotal']
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'method', 'amount']
        read_only_fields = fields


class SaleSerializer(serializers.ModelSerializer):
    details = SaleDetailSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True, default=None)

    class Meta:
        model = Sale
        fields = [
            'id', 'branch', 'cash_register', 'cash_shift', 'client', 'client_name',
            'client_uuid', 'occurred_at',
            'subtotal', 'discount_amount', 'tax_amount', 'total', 'status',
            'details', 'payments', 'company', 'created_at',
        ]
        read_only_fields = fields


class SaleLineInputSerializer(serializers.Serializer):
    """product_id/batch_id sin PrimaryKeyRelatedField ni TenantScopedFieldsMixin
    a propósito: esto se declara como `many=True` dentro de SaleCreateSerializer,
    y un nested serializer declarado como atributo de clase se instancia una
    sola vez al importar el módulo — sin `request` disponible todavía, el
    mixin no tendría nada que acotar (context solo llega vía bind() en
    runtime, después de __init__). Se resuelven contra `.objects.for_user(...)`
    a mano en el ViewSet, mismo patrón que OpenShiftInputSerializer.cash_register_id.
    """

    product_id = serializers.IntegerField()
    batch_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal('0.001'))
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))


class PaymentInputSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))


class SaleCreateSerializer(TenantScopedFieldsMixin, serializers.Serializer):
    # A diferencia de SaleLineInputSerializer, `cash_shift`/`client` SÍ
    # pueden usar el mixin: SaleCreateSerializer se instancia una vez por
    # request en la vista (con context={'request': request}), así que su
    # __init__ ve el request real a tiempo de acotar el queryset.
    tenant_scoped_fields = ('cash_shift', 'client')

    cash_shift = serializers.PrimaryKeyRelatedField(queryset=CashShift.objects.all())
    client = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all(), required=False, allow_null=True)
    occurred_at = serializers.DateTimeField(required=False)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0'))
    client_uuid = serializers.UUIDField(required=False)
    details = SaleLineInputSerializer(many=True)
    payments = PaymentInputSerializer(many=True)
