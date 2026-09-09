from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User
from .forms import CustomUserCreationForm, CustomUserChangeForm


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Interface d'administration des comptes -- GLOBALE (schéma public
    uniquement, `users` n'étant plus listé que dans SHARED_APPS). Le
    rôle applicatif et les rattachements (organisation/établissement/
    badges), propres à chaque tenant, se gèrent désormais dans
    l'admin de chaque tenant via `adhesions.MembreTenant`
    (voir adhesions/admin.py), pas ici.
    """
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User

    list_display = ('username', 'email', 'nom_complet', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'is_verified', 'groups')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'phone_number')
    ordering = ('username',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Informations personnelles'), {
            'fields': ('first_name', 'last_name', 'email', 'phone_number', 'address', 'date_of_birth', 'profile_picture'),
        }),
        (_('Préférences'), {
            'classes': ('collapse',),
            'fields': ('language_preference', 'timezone'),
        }),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions'),
        }),
        (_('Connexion'), {
            'classes': ('collapse',),
            'fields': ('last_login', 'last_login_ip', 'date_joined'),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )

    readonly_fields = ('last_login', 'last_login_ip', 'date_joined')

    @admin.display(description=_('Nom complet'))
    def nom_complet(self, obj):
        return obj.get_full_name()

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return True
        if request.user.is_superuser:
            return True
        # Un utilisateur non-superuser ne peut pas modifier un compte superuser.
        return obj.is_superuser is False
