from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import log_action
from core.permissions import IsAdministratorOrSupervisor
from reports import services
from reports.excel import build_excel_response, build_multi_sheet_excel_response
from reports.serializers import (
    BranchOnlyReportQuerySerializer,
    DateRangeReportQuerySerializer,
    NearExpiryReportQuerySerializer,
    SalesByProductQuerySerializer,
    ShiftDetailReportQuerySerializer,
)
from sales.models import CashShift
from tenants.models import Branch, UserProfile

# Punto 11: exportación a Excel de "los 4 reportes existentes" (los que ya
# estaban en ReportsScreen antes de esta sesión: ventas por producto/
# categoría/cajero -un solo endpoint con group_by-, valuación de
# inventario, mermas por caducidad y cierres de caja). near-expiry-stock
# (punto 4 de esta misma sesión) y sales-by-payment-method (nunca tuvo tab
# en el frontend, gap real encontrado al revisar este archivo -no es scope
# de este punto arreglarlo-) se quedan fuera a propósito, no por olvido.
_SALES_BY_PRODUCT_COLUMNS = {
    'product': [('Producto', 'product_name'), ('Categoría', 'category_name'), ('Cantidad vendida', 'quantity_sold'), ('Ingreso', 'revenue'), ('IVA', 'tax')],
    'category': [('Categoría', 'category_name'), ('Cantidad vendida', 'quantity_sold'), ('Ingreso', 'revenue'), ('IVA', 'tax')],
    'cashier': [('Cajero', 'cashier_email'), ('Cantidad vendida', 'quantity_sold'), ('Ingreso', 'revenue'), ('IVA', 'tax')],
}

_INVENTORY_VALUATION_COLUMNS = [
    ('Producto', 'product_name'), ('Categoría', 'category_name'), ('Cantidad', 'quantity'), ('Valor', 'valuation'),
]

_EXPIRED_STOCK_COLUMNS = [
    ('Producto', 'product_name'), ('Lote', 'batch_number'), ('Sucursal', 'branch_name'),
    ('Caducó', 'expiration_date'), ('Cantidad', 'quantity'), ('Valor', 'valuation'),
]

_CASH_SHIFT_CLOSURES_COLUMNS = [
    ('Sucursal', 'branch_name'), ('Caja', 'register_name'), ('Cajero', 'user_email'),
    ('Apertura', 'opened_at'), ('Cierre', 'closed_at'), ('Fondo inicial', 'opening_balance'),
    ('Efectivo esperado', 'expected_closing_balance'), ('Efectivo contado', 'actual_closing_balance'),
    ('Diferencia efectivo', 'cash_difference'), ('Vouchers esperados', 'expected_voucher_total'),
    ('Vouchers contados', 'actual_voucher_total'), ('Diferencia vouchers', 'voucher_difference'),
]

# Observación de sesión (ronda "3 piezas", punto 3): drill-down de un solo
# turno — tres hojas porque el reporte tiene tres tablas de forma distinta
# (resumen de una fila, pagos por método, abonos a crédito), no una sola
# tabla plana como el resto.
_SHIFT_DETAIL_SUMMARY_COLUMNS = [
    ('Sucursal', 'branch_name'), ('Caja', 'register_name'), ('Cajero', 'user_email'),
    ('Apertura', 'opened_at'), ('Cierre', 'closed_at'), ('Fondo inicial', 'opening_balance'),
    ('Efectivo esperado', 'expected_closing_balance'), ('Efectivo contado', 'actual_closing_balance'),
    ('Diferencia efectivo', 'cash_difference'), ('Vouchers esperados', 'expected_voucher_total'),
    ('Vouchers contados', 'actual_voucher_total'), ('Diferencia vouchers', 'voucher_difference'),
    ('Ventas (cantidad)', 'sales_count'), ('Ventas (total)', 'sales_total'),
    ('Abonos a crédito (total)', 'credit_payments_total'),
]
_SHIFT_DETAIL_PAYMENTS_COLUMNS = [('Método', 'method_label'), ('Total', 'total')]
_SHIFT_DETAIL_CREDIT_COLUMNS = [('Cliente', 'client_name'), ('Monto', 'amount'), ('Fecha', 'created_at')]

# Observación de sesión (ronda de 4 piezas, punto 4): ajustes manuales de
# stock con su motivo — reporte aparte de "Mermas por caducidad" (ver
# reports.services.inventory_adjustments).
_INVENTORY_ADJUSTMENTS_COLUMNS = [
    ('Producto', 'product_name'), ('Lote', 'batch_number'), ('Sucursal', 'branch_name'),
    ('Ajuste', 'quantity_delta'), ('Antes', 'quantity_before'), ('Después', 'quantity_after'),
    ('Motivo', 'reason_label'), ('Detalle', 'reason_detail'), ('Quién', 'user_email'), ('Cuándo', 'created_at'),
]


def _wants_excel(request):
    # OJO: no se llama `format` a propósito — DRF reserva ese nombre de
    # query param (URL_FORMAT_OVERRIDE) para su propia negociación de
    # contenido y devuelve un 404 genérico ("No encontrado") ANTES de que
    # el código de esta vista llegue a correr si el valor no matchea
    # ningún renderer registrado (bug real encontrado escribiendo el
    # primer test de este punto, con format=xlsx).
    return request.query_params.get('export') == 'xlsx'


def _log_export(request, report_name, filters):
    # Observación de sesión, punto 3: no es una columna dentro del Excel,
    # es un registro en AuditLog de que alguien exportó — mismo mecanismo
    # ya usado por el resto de acciones sensibles del proyecto (login por
    # supervisor, cancelación de venta, gestión de usuarios), no una
    # bitácora aparte. Sin pantalla nueva para verlo: se consulta como
    # cualquier otro AuditLog (no existe todavía una vista de auditoría en
    # el frontend — construirla es fuera de alcance de este punto).
    log_action(
        company=request.user.profile.company,
        user=request.user,
        action='report.exported',
        changes={'report': report_name, **filters},
    )


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


def _resolve_cashier(request, user_id):
    """Mismo criterio anti-IDOR que _resolve_branch, vía UserProfile (User
    no tiene manager tenant-scoped propio, la company vive en el profile)."""
    if user_id is None:
        return None, None
    profile = UserProfile.objects.for_user(request.user).filter(user_id=user_id).first()
    if profile is None:
        return None, Response({'detail': 'Cajero no encontrado.'}, status=404)
    return profile.user, None


class SalesByProductReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

    def get(self, request):
        query = SalesByProductQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        branch, error_response = _resolve_branch(request, data.get('branch'))
        if error_response is not None:
            return error_response
        cashier, error_response = _resolve_cashier(request, data.get('cashier'))
        if error_response is not None:
            return error_response

        rows = services.sales_by_product(
            company=request.user.profile.company,
            date_from=data['date_from'],
            date_to=data['date_to'],
            branch=branch,
            cashier=cashier,
            group_by=data['group_by'],
        )
        if _wants_excel(request):
            _log_export(request, 'ventas-por-producto', {
                'group_by': data['group_by'], 'date_from': str(data['date_from']), 'date_to': str(data['date_to']),
                'branch': branch.name if branch else None,
            })
            return build_excel_response(
                filename='ventas-por-producto.xlsx',
                columns=_SALES_BY_PRODUCT_COLUMNS[data['group_by']],
                rows=rows,
            )
        return Response(rows)


class InventoryValuationReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

    def get(self, request):
        query = BranchOnlyReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        branch, error_response = _resolve_branch(request, query.validated_data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.inventory_valuation(company=request.user.profile.company, branch=branch)
        if _wants_excel(request):
            _log_export(request, 'valuacion-de-inventario', {'branch': branch.name if branch else None})
            return build_excel_response(
                filename='valuacion-de-inventario.xlsx', columns=_INVENTORY_VALUATION_COLUMNS, rows=rows,
            )
        return Response(rows)


class ExpiredStockReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

    def get(self, request):
        query = BranchOnlyReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        branch, error_response = _resolve_branch(request, query.validated_data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.expired_stock_report(company=request.user.profile.company, branch=branch)
        if _wants_excel(request):
            _log_export(request, 'mermas-por-caducidad', {'branch': branch.name if branch else None})
            return build_excel_response(
                filename='mermas-por-caducidad.xlsx', columns=_EXPIRED_STOCK_COLUMNS, rows=rows,
            )
        return Response(rows)


class NearExpiryStockReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

    def get(self, request):
        query = NearExpiryReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        branch, error_response = _resolve_branch(request, data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.near_expiry_stock_report(
            company=request.user.profile.company, days=data['days'], branch=branch,
        )
        return Response(rows)


class CashShiftClosuresReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

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
        if _wants_excel(request):
            _log_export(request, 'cierres-de-caja', {
                'date_from': str(data['date_from']), 'date_to': str(data['date_to']),
                'branch': branch.name if branch else None,
            })
            return build_excel_response(
                filename='cierres-de-caja.xlsx', columns=_CASH_SHIFT_CLOSURES_COLUMNS, rows=rows,
            )
        return Response(rows)


class CashShiftDetailReportView(APIView):
    """Drill-down de UN turno cerrado — no reemplaza
    CashShiftClosuresReportView (el agregado por rango de fechas), es el
    detalle de un solo renglón de esa lista. Mismo nivel de acceso que el
    resto de reportes (ADMINISTRADOR + Supervisor)."""

    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

    def get(self, request):
        query = ShiftDetailReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        shift = (
            CashShift.objects.for_user(request.user)
            .filter(pk=query.validated_data['shift'])
            .select_related('cash_register', 'cash_register__branch', 'user')
            .first()
        )
        if shift is None:
            return Response({'detail': 'Turno no encontrado.'}, status=404)
        if shift.status != CashShift.Status.CLOSED:
            return Response(
                {'detail': 'Este turno todavía está abierto — el detalle solo aplica a turnos ya cerrados.'},
                status=400,
            )

        data = services.cash_shift_detail(company=request.user.profile.company, shift=shift)
        if _wants_excel(request):
            _log_export(request, 'cierre-de-turno-detallado', {'shift': shift.id})
            return build_multi_sheet_excel_response(
                filename='cierre-de-turno-detallado.xlsx',
                sheets=[
                    ('Resumen', _SHIFT_DETAIL_SUMMARY_COLUMNS, [data]),
                    ('Pagos por método', _SHIFT_DETAIL_PAYMENTS_COLUMNS, data['payments_by_method']),
                    ('Abonos a crédito', _SHIFT_DETAIL_CREDIT_COLUMNS, data['credit_payments']),
                ],
            )
        return Response(data)


class SalesByPaymentMethodReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

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


class InventoryAdjustmentsReportView(APIView):
    """Observación de sesión (ronda de 4 piezas, punto 4): visibilidad del
    motivo detrás de cada ajuste manual de stock — sin esto el motivo
    quedaba enterrado solo en la base de datos."""

    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

    def get(self, request):
        query = DateRangeReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        branch, error_response = _resolve_branch(request, data.get('branch'))
        if error_response is not None:
            return error_response

        rows = services.inventory_adjustments(
            company=request.user.profile.company,
            date_from=data['date_from'],
            date_to=data['date_to'],
            branch=branch,
        )
        if _wants_excel(request):
            _log_export(request, 'ajustes-de-inventario', {
                'date_from': str(data['date_from']), 'date_to': str(data['date_to']),
                'branch': branch.name if branch else None,
            })
            return build_excel_response(
                filename='ajustes-de-inventario.xlsx', columns=_INVENTORY_ADJUSTMENTS_COLUMNS, rows=rows,
            )
        return Response(rows)
