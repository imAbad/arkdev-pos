from decimal import Decimal

from rest_framework import serializers

from core.serializers import TenantScopedFieldsMixin
from sales.models import CashRegister, CashShift


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
