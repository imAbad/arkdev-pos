from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.serializers import TenantScopedFieldsMixin
from tenants.models import Branch, CompanySettings, SupervisorAuthorization, User, UserProfile


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

    tenant_scoped_fields = ('branch',)

    class Meta:
        model = UserProfile
        fields = ['id', 'email', 'is_active', 'branch', 'role', 'capabilities', 'company']
        read_only_fields = ['company']


class UserCreateSerializer(TenantScopedFieldsMixin, serializers.Serializer):
    """Punto 9: alta de usuario del tenant — crea `User` (login) y
    `UserProfile` (branch/role/capabilities) juntos, no es un
    ModelSerializer de UserProfile porque email/password pertenecen al
    modelo `User`, no a UserProfile."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    role = serializers.ChoiceField(choices=UserProfile.Role.choices)
    capabilities = serializers.JSONField(required=False, default=dict)

    tenant_scoped_fields = ('branch',)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con este correo.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value


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
