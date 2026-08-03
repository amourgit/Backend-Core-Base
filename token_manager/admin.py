from django.contrib import admin
from .models import TokenSettings, TokenManager
from django.utils.translation import gettext_lazy as _
# Register your models here.

@admin.register(TokenSettings)
class TokenSettingsAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'is_active')
        }),
        (_('Durée de vie des tokens'), {
            'fields': (
                'access_token_lifetime',
                'refresh_token_lifetime',
            )
        }),
        (_('Cookies'), {
            'fields': (
                'cookie_secure',
                'cookie_samesite',
                'cookie_domain',
            )
        }),
        (_('Sécurité'), {
            'fields': ('max_tokens_per_user',
                       'rotate_refresh_tokens',
                       'blacklist_after_rotation',
                       )
        }),
        (_('Sécurité avancée'), {
            'fields': ('enable_blacklist',
                       'blacklist_cleanup_after',
                       'require_https',
                       'validate_ip',
                       'validate_user_agent',
                       )
        })
    )

@admin.register(TokenManager)
class TokenManagerAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user_id',
        'username',
        'tenant_id',
        'device_family',
        'device_brand',
        'device_model',
        'device_type',
        'os_family',
        'browser_family',
        'ip_address',
        'is_current',
        'is_revoked',
        'created_at',
        'expires_at',
        'last_used',
    )
    search_fields = ('username', 'user_id', 'tenant_id', 'device_family', 'device_brand', 'device_model', 'ip_address')
    list_filter = ('device_type', 'os_family', 'browser_family', 'is_current', 'is_revoked')

    def has_add_permission(self, request):
        return False  # Empêche la création manuelle de tokens

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return True
        return obj.is_revoked  # Permet de modifier uniquement les tokens révoqués

    def has_delete_permission(self, request, obj=None):
        return True  # Permet la suppression des tokens
