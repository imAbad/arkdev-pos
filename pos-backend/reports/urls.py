from django.urls import path

from reports.views import (
    CashShiftClosuresReportView,
    ExpiredStockReportView,
    InventoryValuationReportView,
    NearExpiryStockReportView,
    SalesByPaymentMethodReportView,
    SalesByProductReportView,
)

# Sin DefaultRouter: estas no son vistas CRUD sobre un modelo, son
# consultas de agregación de solo lectura — mismo criterio que las
# @action de sales/viewsets.py para operaciones que no son un ModelViewSet
# genérico.
urlpatterns = [
    path('reports/sales-by-product/', SalesByProductReportView.as_view(), name='report-sales-by-product'),
    path('reports/inventory-valuation/', InventoryValuationReportView.as_view(), name='report-inventory-valuation'),
    path('reports/expired-stock/', ExpiredStockReportView.as_view(), name='report-expired-stock'),
    path('reports/near-expiry-stock/', NearExpiryStockReportView.as_view(), name='report-near-expiry-stock'),
    path('reports/cash-shift-closures/', CashShiftClosuresReportView.as_view(), name='report-cash-shift-closures'),
    path(
        'reports/sales-by-payment-method/',
        SalesByPaymentMethodReportView.as_view(),
        name='report-sales-by-payment-method',
    ),
]
