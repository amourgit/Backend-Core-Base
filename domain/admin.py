from django.contrib import admin
from common.admin import PublicSchemaOnlyAdminMixin
from .models import Domain

# Register your models here.
@admin.register(Domain)
class DomainAdmin(PublicSchemaOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
    list_filter = ('is_primary',)
    search_fields = ('domain', 'tenant__name')
    raw_id_fields = ('tenant',)