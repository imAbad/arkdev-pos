from decimal import Decimal

from rest_framework import serializers

from core.serializers import TenantScopedFieldsMixin
from customers.models import Client, CreditAccount, CreditMovement


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name', 'phone', 'email', 'credit_limit', 'company', 'created_at', 'updated_at']
        read_only_fields = ['company', 'created_at', 'updated_at']


class CreditMovementSerializer(serializers.ModelSerializer):
    """Solo lectura — se crea vía CreditAccountViewSet.pay (y, desde
    sales.services.create_sale, un CARGO automático), nunca directo."""

    class Meta:
        model = CreditMovement
        fields = ['id', 'sale', 'amount', 'type', 'created_at']
        read_only_fields = fields


class CreditAccountSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    # CreditAccountSerializer se instancia una vez por request en el
    # ViewSet (con context real), así que el mixin sí aplica aquí — a
    # diferencia de CreditMovementInputSerializer más abajo, que se maneja
    # a mano por la razón documentada en arquitectura_tecnica_pos.md §5.
    tenant_scoped_fields = ('client',)

    client_name = serializers.CharField(source='client.name', read_only=True)
    movements = CreditMovementSerializer(many=True, read_only=True)

    class Meta:
        model = CreditAccount
        fields = ['id', 'client', 'client_name', 'balance', 'movements', 'company']
        read_only_fields = ['balance', 'movements', 'company']


class CreditMovementInputSerializer(serializers.Serializer):
    """Input para las acciones charge/pay de CreditAccountViewSet.

    `sale_id` NO usa TenantScopedFieldsMixin ni PrimaryKeyRelatedField a
    propósito — sigue la regla ya documentada en arquitectura_tecnica_pos.md
    §5 sobre serializers anidados/de acción: se resuelve a mano contra
    `.objects.for_user(...)` en el ViewSet, igual que
    OpenShiftInputSerializer.cash_register_id y
    SaleLineInputSerializer.product_id/batch_id — no asumir que "importar
    el mixin" alcanza si el campo no pasa por un PrimaryKeyRelatedField
    acotado explícitamente.
    """

    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    sale_id = serializers.IntegerField(required=False, allow_null=True)
