from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.mixins import TenantScopedViewSetMixin
from core.permissions import IsAdministrator, IsAdministratorOrReadOnly
from tenants.models import Branch, CompanySettings, UserProfile
from tenants.serializers import (
    BranchSerializer,
    CompanySettingsSerializer,
    SupervisorAuthorizationRequestSerializer,
    SupervisorAuthorizationSerializer,
    UserCreateSerializer,
    UsernameLoginInputSerializer,
    UserProfileSerializer,
)
from tenants.services import (
    AuthorizationError,
    UserManagementError,
    UsernameLoginError,
    create_tenant_user,
    deactivate_user,
    reactivate_user,
    request_supervisor_authorization,
    request_username_login,
)


class BranchViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer


class CompanySettingsViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = CompanySettings.objects.all()
    serializer_class = CompanySettingsSerializer
    permission_classes = [IsAuthenticated, IsAdministratorOrReadOnly]


class UserProfileViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Punto 9: gestión completa de usuarios del tenant — ADMINISTRADOR
    exclusivo, sin excepción (ni siquiera un Supervisor pasa aquí, a
    diferencia de reportes/inventario: dar de alta/baja gente y ver el
    roster completo -emails, roles, capabilities de todos- es autoridad
    de dueño/gerente, no operativa). `me` es la única acción abierta a
    cualquier autenticado: el login normal de cualquier rol la necesita
    para saber quién es.

    Sin DELETE ni PUT a propósito: borrar un UserProfile dejaría huérfanas
    las referencias de historial (Sale.cashier, CashShift.user, AuditLog)
    y evitaría la salvaguarda del último admin — todo cambio de
    activo/inactivo pasa por deactivate/reactivate, nunca por un DELETE
    genérico."""

    queryset = UserProfile.objects.select_related('user', 'branch').all()
    serializer_class = UserProfileSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action == 'me':
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsAdministrator()]

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
        return Response(UserProfileSerializer(profile, context={'request': request}).data)

    def create(self, request, *args, **kwargs):
        # No es un ModelSerializer de UserProfile: email/password son del
        # modelo User, así que create_tenant_user arma ambos juntos (ver
        # tenants.services) en vez de que perform_create/TenantScopedViewSetMixin
        # intenten guardar un UserProfile a medias.
        input_serializer = UserCreateSerializer(data=request.data, context={'request': request})
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        profile = create_tenant_user(
            email=data['email'], password=data['password'], branch=data['branch'],
            role=data['role'], capabilities=data.get('capabilities'), actor=request.user,
            username=data['username'], date_of_birth=data['date_of_birth'],
        )
        return Response(
            UserProfileSerializer(profile, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        target_profile = self.get_object()
        try:
            deactivate_user(target_profile=target_profile, actor=request.user)
        except UserManagementError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UserProfileSerializer(target_profile, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        target_profile = self.get_object()
        reactivate_user(target_profile=target_profile, actor=request.user)
        return Response(UserProfileSerializer(target_profile, context={'request': request}).data)


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


class UsernameLoginView(APIView):
    """Punto 5: login alterno de mostrador (username + fecha de
    nacimiento) — emite el mismo tipo de token que
    TokenObtainPairView (SimpleJWT), no un sistema de auth paralelo. Sin
    autenticar (AllowAny): es justo la puerta de entrada, como
    /auth/token/."""

    permission_classes = [AllowAny]

    def post(self, request):
        input_serializer = UsernameLoginInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        try:
            user = request_username_login(username=data['username'], date_of_birth=data['date_of_birth'])
        except UsernameLoginError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh)})
