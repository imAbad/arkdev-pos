from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from tenants.models import Branch, Company, CompanySettings, SupervisorAuthorization, User, UserProfile


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ('email',)
    list_display = ('email', 'is_staff', 'is_active')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'password1', 'password2')}),
    )
    search_fields = ('email',)


admin.site.register(Company)
admin.site.register(Branch)
admin.site.register(CompanySettings)
admin.site.register(UserProfile)


@admin.register(SupervisorAuthorization)
class SupervisorAuthorizationAdmin(admin.ModelAdmin):
    list_display = ('supervisor', 'requested_by', 'reason', 'expires_at', 'used_at')
    readonly_fields = [f.name for f in SupervisorAuthorization._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
