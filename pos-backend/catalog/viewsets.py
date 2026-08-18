from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from catalog.models import Batch, Category, Product, Supplier
from catalog.serializers import BatchSerializer, CategorySerializer, ProductSerializer, SupplierSerializer
from core.mixins import TenantScopedViewSetMixin


class CategoryViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]


class SupplierViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]


class ProductViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]


class BatchViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    permission_classes = [IsAuthenticated]
