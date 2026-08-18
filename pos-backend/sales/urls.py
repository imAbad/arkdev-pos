from rest_framework.routers import DefaultRouter

from sales.viewsets import CashRegisterViewSet, CashShiftViewSet

router = DefaultRouter()
router.register('cash-registers', CashRegisterViewSet, basename='cash-register')
router.register('cash-shifts', CashShiftViewSet, basename='cash-shift')

urlpatterns = router.urls
