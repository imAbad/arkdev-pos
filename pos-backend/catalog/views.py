from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.services import low_stock_products
from core.permissions import HandlesCash


class LowStockView(APIView):
    """Punto 7: visibilidad de stock bajo al abrir turno — mismo gate que
    CashShiftViewSet (HandlesCash), no restringido a admin/supervisor:
    cualquier cajero que abre turno debe poder verlo, no solo quien
    genera reportes."""

    permission_classes = [IsAuthenticated, HandlesCash]

    def get(self, request):
        rows = low_stock_products(company=request.user.profile.company)
        return Response(rows)
