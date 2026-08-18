from rest_framework import serializers

from tenants.models import Branch, CompanySettings, SupervisorAuthorization, UserProfile


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'address', 'company', 'created_at', 'updated_at']
        read_only_fields = ['company', 'created_at', 'updated_at']


class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanySettings
        fields = ['id', 'company', 'enabled_modules', 'created_at', 'updated_at']
        read_only_fields = ['company', 'created_at', 'updated_at']


class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'email', 'branch', 'role', 'capabilities', 'company']
        read_only_fields = ['company']


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
