from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdministrator
from reports import services
from reports.serializers import (
    BranchOnlyReportQuerySerializer,
    DateRangeReportQuerySerializer,
    SalesByProductQuerySerializer,
)
from tenants.models import Branch


def _resolve_branch(request, branch_id):
    """Un `branch` en query params se resuelve contra `.for_user(...)`, no
    contra `Branch.objects.get(pk=...)` directo — mismo motivo que
    tenant_scoped_fields en SaleCreateSerializer: sin esto, alguien podría
    pasar el id de una sucursal de OTRO tenant y el reporte filtraría
    (erróneamente) por ella en vez de rechazarla."""
    if branch_id is None:
        return None, None
    branch = Branch.objects.for_user(request.user).filter(pk=branch_id).first()
    if branch is None:
        return None, Response({'detail': 'Sucursal no encontrada.'}, status=404)
    return branch, None


class SalesByProductReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request):
        query = SalesByProductQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        branch, error_response = _resolve_branch(request, data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.sales_by_product(
            company=request.user.profile.company,
            date_from=data['date_from'],
            date_to=data['date_to'],
            branch=branch,
            group_by=data['group_by'],
        )
        return Response(rows)


class InventoryValuationReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request):
        query = BranchOnlyReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        branch, error_response = _resolve_branch(request, query.validated_data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.inventory_valuation(company=request.user.profile.company, branch=branch)
        return Response(rows)


class ExpiredStockReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request):
        query = BranchOnlyReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        branch, error_response = _resolve_branch(request, query.validated_data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.expired_stock_report(company=request.user.profile.company, branch=branch)
        return Response(rows)


class CashShiftClosuresReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request):
        query = DateRangeReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        branch, error_response = _resolve_branch(request, data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.cash_shift_closures(
            company=request.user.profile.company,
            date_from=data['date_from'],
            date_to=data['date_to'],
            branch=branch,
        )
        return Response(rows)


class SalesByPaymentMethodReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request):
        query = DateRangeReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        branch, error_response = _resolve_branch(request, data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.sales_summary_by_payment_method(
            company=request.user.profile.company,
            date_from=data['date_from'],
            date_to=data['date_to'],
            branch=branch,
        )
        return Response(rows)
