from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import Batch, Product
from core.mixins import TenantScopedViewSetMixin
from core.permissions import HandlesCash
from sales.models import CashRegister, CashShift, Sale
from sales.serializers import (
    CashRegisterSerializer,
    CashShiftSerializer,
    CloseShiftInputSerializer,
    OpenShiftInputSerializer,
    SaleCreateSerializer,
    SaleSerializer,
)
from sales.services import SaleError, ShiftError, ShiftPermissionError
from sales.services import close_shift as close_shift_service
from sales.services import create_sale as create_sale_service
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


class SaleViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Solo lectura por los endpoints estándar — registrar una venta es una
    operación de negocio con reglas propias (turno abierto, descuento de
    stock por lote, pagos que deben sumar el total exacto), no un POST
    genérico de creación."""

    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated, HandlesCash]

    @action(detail=False, methods=['post'], url_path='create-sale')
    def create_sale(self, request):
        input_serializer = SaleCreateSerializer(data=request.data, context={'request': request})
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        resolved_details = []
        for line in data['details']:
            product = Product.objects.for_user(request.user).filter(pk=line['product_id']).first()
            if product is None:
                return Response(
                    {'detail': f"Producto {line['product_id']} no encontrado."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            batch = None
            batch_id = line.get('batch_id')
            if batch_id is not None:
                batch = Batch.objects.for_user(request.user).filter(pk=batch_id).first()
                if batch is None:
                    return Response({'detail': f'Lote {batch_id} no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

            resolved_details.append({
                'product': product,
                'batch': batch,
                'quantity': line['quantity'],
                'unit_price': line['unit_price'],
            })

        try:
            sale = create_sale_service(
                cash_shift=data['cash_shift'],
                details=resolved_details,
                payments=data['payments'],
                occurred_at=data.get('occurred_at'),
                discount_amount=data['discount_amount'],
                client_uuid=data.get('client_uuid'),
            )
        except SaleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(sale).data, status=status.HTTP_201_CREATED)
