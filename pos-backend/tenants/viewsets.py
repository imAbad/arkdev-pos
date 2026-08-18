from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import TenantScopedViewSetMixin
from core.permissions import IsAdministratorOrReadOnly
from tenants.models import Branch, CompanySettings, UserProfile
from tenants.serializers import (
    BranchSerializer,
    CompanySettingsSerializer,
    SupervisorAuthorizationRequestSerializer,
    SupervisorAuthorizationSerializer,
    UserProfileSerializer,
)
from tenants.services import AuthorizationError, request_supervisor_authorization


class BranchViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer


class CompanySettingsViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = CompanySettings.objects.all()
    serializer_class = CompanySettingsSerializer
    permission_classes = [IsAuthenticated, IsAdministratorOrReadOnly]


class UserProfileViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Solo lectura por ahora: un panel de administración de staff (editar
    role/capabilities vía API) es trabajo de frontend/admin todavía no
    construido (punto 7), no depende de esta pieza."""

    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer

    @action(detail=False, methods=['get'])
    def me(self, request):
        # El frontend necesita saber quién es (branch, role, capabilities)
        # justo después de login, sin tener que adivinar cuál fila del
        # listado (todo el tenant) le corresponde.
        profile = getattr(request.user, 'profile', None)
        if profile is None:
            return Response(
                {'detail': 'Tu usuario no tiene un perfil de tenant asociado.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(self.get_serializer(profile).data)


class RequestSupervisorAuthorizationView(APIView):
    """PIN/reautenticación para `can_authorize_exceptions` (punto 6).

    No es un ViewSet: no hay CRUD de SupervisorAuthorization desde el
    cliente, solo "solicitar una". `request.user` es el cajero ya
    autenticado (su sesión/JWT no se toca); el body trae las credenciales
    del SUPERVISOR a validar.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        input_serializer = SupervisorAuthorizationRequestSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        try:
            authorization = request_supervisor_authorization(
                requesting_user=request.user,
                email=data['email'],
                password=data['password'],
                reason=data.get('reason', ''),
            )
        except AuthorizationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        return Response(
            SupervisorAuthorizationSerializer(authorization).data,
            status=status.HTTP_201_CREATED,
        )
