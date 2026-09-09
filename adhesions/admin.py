from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import Badge, MembreTenant

User = get_user_model()


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('nom', 'icone', 'description')
    search_fields = ('nom',)


@admin.register(MembreTenant)
class MembreTenantAdmin(admin.ModelAdmin):
    """
    Gestion des membres DE CE TENANT (rôle, organisation, établissement,
    badges, statut d'adhésion). `user_id` référence l'identité globale
    (users.User, schéma public) SANS ForeignKey physique -- voir
    adhesions/models.py -- d'où l'usage d'un simple champ entier plutôt
    que d'un autocomplete_fields Django (qui suppose une vraie FK).
    """
    list_display = ('user_id', 'nom_utilisateur', 'role', 'organisation', 'etablissement', 'statut_adhesion', 'cree_le')
    list_filter = ('role', 'statut_adhesion')
    search_fields = ('user_id',)
    autocomplete_fields = ['organisation', 'etablissement', 'badges']
    readonly_fields = ('demande_le', 'traitee_le')

    fieldsets = (
        (None, {'fields': ('user_id',)}),
        (_('Rattachement dans ce tenant'), {
            'fields': ('role', 'organisation', 'etablissement', 'badges'),
        }),
        (_('Adhésion'), {
            'fields': ('statut_adhesion', 'demande_le', 'traitee_le', 'traitee_par_id', 'motif_refus'),
        }),
    )

    @admin.display(description=_('Utilisateur (identité globale)'))
    def nom_utilisateur(self, obj):
        u = User.objects.filter(id=obj.user_id).first()
        return u.username if u else f"#{obj.user_id} (introuvable)"
