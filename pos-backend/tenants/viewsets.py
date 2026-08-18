from rest_framework import viewsets

from core.mixins import TenantScopedViewSetMixin
from tenants.models import Branch, CompanySettings, UserProfile
from tenants.serializers import (
    BranchSerializer,
    CompanySettingsSerializer,
    UserProfileSerializer,
)


class BranchViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer


class CompanySettingsViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = CompanySettings.objects.all()
    serializer_class = CompanySettingsSerializer


class UserProfileViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Solo lectura por ahora: editar role/capabilities es parte de la
    capability can_authorize_exceptions (paso 6 del orden de construcción),
    todavía no construida."""

    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
