from rest_framework import serializers

from tenants.models import Branch, CompanySettings, UserProfile


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
