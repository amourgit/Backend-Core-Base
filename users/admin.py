from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User
from tenants.models import Tenant
from .forms import CustomUserCreationForm, CustomUserChangeForm

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Custom administration interface for users.
    Each tenant sees only their own users.
    """
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('last_login', 'date_joined')
    
    def get_queryset(self, request):
        """
        Filter users to show only those of the current tenant.
        """
        qs = super().get_queryset(request)
        # REMOVE this part:
        # if not request.user.is_superuser:
        #     return qs.filter(tenant=request.user.tenant)
        return qs

    def has_change_permission(self, request, obj=None):
        """
        Check if the user has permission to modify the object.
        """
        if obj is None:
            return True
        if request.user.is_superuser:
            return True
        # A user can only modify users of their tenant
        return obj.is_superuser is False and obj.id in User.objects.filter(id=obj.id).values_list('id', flat=True)
