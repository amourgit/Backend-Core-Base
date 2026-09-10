from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Badge
from .forms import CustomUserCreationForm, CustomUserChangeForm


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('nom', 'icone', 'description')
    search_fields = ('nom',)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Interface d'administration des utilisateurs. Chaque tenant (schéma)
    ne voit que ses propres utilisateurs — l'isolation est assurée par
    django-tenants au niveau du schéma PostgreSQL, pas par un filtre
    applicatif ici.
    """
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User

    list_display = ('username', 'email', 'nom_complet', 'role', 'etablissement', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'is_verified', 'role', 'groups')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'phone_number')
    ordering = ('username',)
    autocomplete_fields = ['etablissement', 'organisation', 'badges']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Informations personnelles'), {
            'fields': ('first_name', 'last_name', 'email', 'phone_number', 'address', 'date_of_birth', 'profile_picture'),
        }),
        (_('CIVITAS NEWS'), {
            'description': _("Rôle applicatif et rattachement — pilote les permissions frontend et backend."),
            'fields': ('role', 'etablissement', 'organisation', 'badges'),
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
            'fields': ('username', 'email', 'role', 'password1', 'password2'),
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
