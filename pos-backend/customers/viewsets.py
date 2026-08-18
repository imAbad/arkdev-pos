from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.mixins import TenantScopedViewSetMixin
from customers.models import Client, CreditAccount
from customers.serializers import CreditAccountSerializer, CreditMovementInputSerializer, ClientSerializer
from customers.services import CreditError, pay_credit
from sales.models import Sale


class ClientViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]


class CreditAccountViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Solo lectura por los endpoints estándar — los movimientos de crédito
    (CreditMovement, anidado aquí) se crean vía `pay`, nunca con un POST
    genérico que pueda desincronizar `balance` de la suma de movimientos."""

    queryset = CreditAccount.objects.all()
    serializer_class = CreditAccountSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        account = self.get_object()
        input_serializer = CreditMovementInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        sale = None
        sale_id = data.get('sale_id')
        if sale_id is not None:
            sale = Sale.objects.for_user(request.user).filter(pk=sale_id).first()
            if sale is None:
                return Response({'detail': f'Venta {sale_id} no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            account = pay_credit(account=account, amount=data['amount'], sale=sale)
        except CreditError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(account).data, status=status.HTTP_200_OK)
