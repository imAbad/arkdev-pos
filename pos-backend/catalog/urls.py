from django.urls import path
from rest_framework.routers import DefaultRouter

from catalog.viewsets import BatchViewSet, CategoryViewSet, ProductViewSet, SupplierViewSet
from catalog.views import LowStockView

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('suppliers', SupplierViewSet, basename='supplier')
router.register('products', ProductViewSet, basename='product')
router.register('batches', BatchViewSet, basename='batch')

urlpatterns = [
    path('low-stock/', LowStockView.as_view(), name='low-stock'),
] + router.urls
