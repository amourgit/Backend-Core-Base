from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from common.admin import PublicSchemaOnlyAdminMixin
from .models import Tenant

@admin.register(Tenant)
class TenantAdmin(PublicSchemaOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'schema_name', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'schema_name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'schema_name', 'is_active')
        }),
        (_('Description'), {
            'fields': ('description',)
        }),
    )

