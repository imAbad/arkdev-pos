from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.mixins import TenantScopedViewSetMixin
from core.permissions import HandlesCash
from sales.models import CashRegister, CashShift
from sales.serializers import (
    CashRegisterSerializer,
    CashShiftSerializer,
    CloseShiftInputSerializer,
    OpenShiftInputSerializer,
)
from sales.services import ShiftError, ShiftPermissionError
from sales.services import close_shift as close_shift_service
from sales.services import open_shift as open_shift_service


class CashRegisterViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = CashRegister.objects.all()
    serializer_class = CashRegisterSerializer
    permission_classes = [IsAuthenticated, HandlesCash]


class CashShiftViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Solo lectura por los endpoints estándar — abrir/cerrar turno son
    operaciones de negocio con reglas propias (constraint de unicidad,
    arqueo ciego, autorización de excepción), no un PATCH genérico."""

    queryset = CashShift.objects.all()
    serializer_class = CashShiftSerializer
    permission_classes = [IsAuthenticated, HandlesCash]

    @action(detail=False, methods=['post'], url_path='open-shift')
    def open_shift(self, request):
        input_serializer = OpenShiftInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        cash_register = CashRegister.objects.for_user(request.user).filter(
            pk=input_serializer.validated_data['cash_register_id'],
        ).first()
        if cash_register is None:
            return Response({'detail': 'Caja no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            shift = open_shift_service(
                user=request.user,
                cash_register=cash_register,
                opening_balance=input_serializer.validated_data['opening_balance'],
            )
        except ShiftError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(shift).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close-shift')
    def close_shift(self, request, pk=None):
        shift = self.get_object()
        input_serializer = CloseShiftInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            shift = close_shift_service(
                shift=shift,
                closing_user=request.user,
                actual_closing_balance=input_serializer.validated_data['actual_closing_balance'],
                actual_voucher_total=input_serializer.validated_data['actual_voucher_total'],
            )
        except ShiftError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ShiftPermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        return Response(self.get_serializer(shift).data, status=status.HTTP_200_OK)
