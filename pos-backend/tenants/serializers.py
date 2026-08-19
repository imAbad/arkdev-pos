from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.settings import api_settings as simplejwt_settings

from core.serializers import TenantScopedFieldsMixin
from tenants.models import Branch, CompanySettings, SupervisorAuthorization, User, UserProfile
from tenants.services import authenticate_by_identifier


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'address', 'company', 'created_at', 'updated_at']
        read_only_fields = ['company', 'created_at', 'updated_at']


class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanySettings
        fields = [
            'id', 'company', 'enabled_modules',
            'business_name', 'logo', 'accent_color',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['company', 'created_at', 'updated_at']


class UserProfileSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    tenant_scoped_fields = ('branch',)

    class Meta:
        model = UserProfile
        fields = ['id', 'email', 'username', 'is_active', 'branch', 'role', 'capabilities', 'date_of_birth', 'company']
        read_only_fields = ['company']


class UserCreateSerializer(TenantScopedFieldsMixin, serializers.Serializer):
    """Punto 9: alta de usuario del tenant — crea `User` (login) y
    `UserProfile` (branch/role/capabilities) juntos, no es un
    ModelSerializer de UserProfile porque email/password pertenecen al
    modelo `User`, no a UserProfile.

    Corrección de sesión: `username` es el único identificador
    obligatorio (antes se pedían username+fecha_nacimiento juntos para
    un login alterno que ya no existe) — `email` pasa a ser opcional,
    puede entrar solo por username."""

    email = serializers.EmailField(required=False, allow_blank=True, default='')
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    role = serializers.ChoiceField(choices=UserProfile.Role.choices)
    capabilities = serializers.JSONField(required=False, default=dict)
    username = serializers.CharField(max_length=30)
    # Dato de perfil administrativo, sin relación con el login (ver
    # UserProfile.date_of_birth) — opcional.
    date_of_birth = serializers.DateField(required=False, allow_null=True, default=None)

    tenant_scoped_fields = ('branch',)

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con este correo.')
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con este nombre de usuario.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value


class IdentifierTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Reemplaza el TokenObtainPairSerializer estándar de SimpleJWT (que
    solo acepta `USERNAME_FIELD`, o sea email) para aceptar `username` O
    `email` como identificador — misma cuenta, misma contraseña, dos
    formas de identificarse. No delega en `authenticate()`/
    AUTHENTICATION_BACKENDS de Django: resuelve directo contra
    `tenants.services.authenticate_by_identifier`, un solo camino
    explícito en vez de plomería genérica pluggable que no se necesita
    aquí."""

    username_field = 'identifier'

    def validate(self, attrs):
        user = authenticate_by_identifier(identifier=attrs.get('identifier', ''), password=attrs['password'])
        if user is None:
            raise AuthenticationFailed(
                self.error_messages['no_active_account'], 'no_active_account',
            )
        self.user = user
        refresh = self.get_token(self.user)
        data = {'refresh': str(refresh), 'access': str(refresh.access_token)}
        if simplejwt_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)
        return data


class SupervisorAuthorizationRequestSerializer(serializers.Serializer):
    """Credenciales del SUPERVISOR, no del cajero que hace el request (ese
    ya viene autenticado por el JWT normal — este endpoint no lo toca)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class SupervisorAuthorizationSerializer(serializers.ModelSerializer):
    supervisor_email = serializers.EmailField(source='supervisor.email', read_only=True)

    class Meta:
        model = SupervisorAuthorization
        fields = ['token', 'supervisor_email', 'reason', 'expires_at']
        read_only_fields = fields
