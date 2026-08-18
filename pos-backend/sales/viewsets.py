from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import Batch, Product
from core.mixins import TenantScopedViewSetMixin
from core.permissions import HandlesCash
from sales.emails import TicketEmailError, send_sale_ticket_email
from sales.models import CashRegister, CashShift, Sale
from sales.serializers import (
    CancelSaleInputSerializer,
    CashRegisterSerializer,
    CashShiftSerializer,
    CloseShiftInputSerializer,
    OpenShiftInputSerializer,
    SaleCreateSerializer,
    SaleSerializer,
    SendTicketEmailInputSerializer,
)
from sales.services import RegisterAlreadyOpenError, SaleCancellationError, SaleError, ShiftError, ShiftPermissionError
from sales.services import cancel_sale as cancel_sale_service
from sales.services import close_shift as close_shift_service
from sales.services import create_sale as create_sale_service
from sales.services import open_shift as open_shift_service
from tenants.models import CompanySettings


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

    @action(detail=False, methods=['get'])
    def current(self, request):
        # El frontend necesita saber, al entrar, si el cajero ya tiene un
        # turno abierto (ej. recargó la página) para saltarse la pantalla
        # de apertura en vez de chocar con "ya tienes un turno abierto".
        shift = self.get_queryset().filter(user=request.user, status=CashShift.Status.OPEN).first()
        if shift is None:
            return Response({'detail': 'No tienes un turno abierto.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(shift).data)

    @action(detail=False, methods=['get'], url_path='for-register')
    def for_register(self, request):
        # A diferencia de `current` (solo el turno del usuario logueado),
        # esto expone el turno abierto de una caja sea de quien sea —
        # necesario para que admin/supervisor puedan VER que hay un turno
        # varado ahí antes de decidir qué hacer con él (punto 0). Ver
        # también qué puede HACER con ese turno depende de su rol/
        # capability, pero verlo (quién lo abrió, cuándo) no requiere esa
        # autoridad — mismo criterio que ya usa close_shift para permitir
        # el override, no uno nuevo.
        cash_register_id = request.query_params.get('cash_register_id')
        if not cash_register_id:
            return Response({'detail': 'cash_register_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        shift = self.get_queryset().filter(
            cash_register_id=cash_register_id, status=CashShift.Status.OPEN,
        ).select_related('user', 'cash_register').first()
        if shift is None:
            return Response({'detail': 'Esta caja no tiene un turno abierto.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(shift).data)

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
        except RegisterAlreadyOpenError as exc:
            return Response({'code': 'register_already_open', 'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
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
                client=data.get('client'),
                details=resolved_details,
                payments=data['payments'],
                occurred_at=data.get('occurred_at'),
                discount_amount=data['discount_amount'],
                client_uuid=data.get('client_uuid'),
            )
        except SaleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(sale).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        sale = self.get_object()
        input_serializer = CancelSaleInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            sale = cancel_sale_service(
                sale=sale,
                actor=request.user,
                supervisor_authorization_token=input_serializer.validated_data['supervisor_authorization_token'],
            )
        except SaleCancellationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(sale).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='send-ticket-email')
    def send_ticket_email(self, request, pk=None):
        sale = self.get_object()
        input_serializer = SendTicketEmailInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        company_settings = CompanySettings.objects.filter(company=sale.company).first()
        business_name = (company_settings.business_name if company_settings else '') or 'Punto de Venta'

        try:
            send_sale_ticket_email(
                sale=sale,
                business_name=business_name,
                to_email=data['email'],
                change_given=data.get('change_given'),
            )
        except TicketEmailError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({'detail': 'Ticket enviado.'}, status=status.HTTP_200_OK)
