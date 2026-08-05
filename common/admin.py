"""
Mixins d'administration communs — appliqués par tous les `admin.py`
des apps métier pour exposer le Socle de Traçabilité de façon uniforme.
"""

from django.contrib import admin
from django.db import connection
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name


class PublicSchemaOnlyAdminMixin:
    """
    Restreint un ModelAdmin au schéma PUBLIC (admin global de plateforme).

    Contexte : django.contrib.admin.site est un registre Python unique pour
    tout le process — il ne "sait" pas dans quel schéma tenant on se trouve.
    Un modèle enregistré (ex: Tenant, Domain) reste donc visible/éditable
    depuis N'IMPORTE QUEL admin de tenant dès lors que l'utilisateur local
    de ce tenant a is_superuser=True (ce qui est le cas du compte créé
    automatiquement pour chaque établissement). Comme les tables de ces
    modèles vivent uniquement dans le schéma public (apps SHARED_APPS), le
    search_path de django-tenants ([schema_tenant, public]) les rend malgré
    tout accessibles depuis un tenant — une vraie fuite inter-tenant.

    Ce mixin ferme cette fuite : en plus d'exiger is_superuser, il exige
    que la requête soit servie depuis le schéma public.
    """

    def _is_public_schema(self):
        return connection.schema_name == get_public_schema_name()

    def has_view_permission(self, request, obj=None):
        return self._is_public_schema() and request.user.is_superuser

    def has_module_permission(self, request):
        return self._is_public_schema() and request.user.is_superuser

    def has_add_permission(self, request):
        return self._is_public_schema() and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return self._is_public_schema() and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return self._is_public_schema() and request.user.is_superuser


SOCLE_READONLY_FIELDS = (
    'id', 'cree_le', 'cree_par', 'cree_par_systeme',
    'modifie_le', 'modifie_par', 'modifie_par_systeme',
    'version', 'supprime_le', 'supprime_par',
)

SOCLE_FIELDSET = (_('Socle de Traçabilité'), {
    'classes': ('collapse',),
    'fields': (
        ('cree_le', 'cree_par', 'cree_par_systeme'),
        ('modifie_le', 'modifie_par', 'modifie_par_systeme'),
        ('version', 'statut', 'origine_donnee'),
        'motif_derniere_modification',
        ('supprime_le', 'supprime_par'),
    ),
})

# Variante pour les entités qui redéfinissent `statut` avec leur propre
# cycle de vie métier (ex: News, Sondage, Signalement — voir le
# docstring de SocleTracabilite dans common/models.py) : `statut` est
# alors affiché dans la section métier plutôt qu'ici, pour rester bien
# visible plutôt que noyé dans une section technique repliée.
SOCLE_FIELDSET_SANS_STATUT = (_('Socle de Traçabilité'), {
    'classes': ('collapse',),
    'fields': (
        ('cree_le', 'cree_par', 'cree_par_systeme'),
        ('modifie_le', 'modifie_par', 'modifie_par_systeme'),
        ('version', 'origine_donnee'),
        'motif_derniere_modification',
        ('supprime_le', 'supprime_par'),
    ),
})


class TracabiliteAdminMixin(admin.ModelAdmin):
    """Mixin à utiliser sur tout ModelAdmin d'une entité héritant de
    `common.models.SocleTracabilite`. Rend le socle visible mais protégé en
    écriture, et trace automatiquement l'utilisateur admin qui modifie."""

    readonly_fields = SOCLE_READONLY_FIELDS

    def get_list_filter(self, request):
        return tuple(self.list_filter) + ('statut', 'origine_donnee')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.cree_par = request.user
        else:
            obj.modifie_par = request.user
            if not obj.motif_derniere_modification:
                obj.motif_derniere_modification = _('Modification via l’interface d’administration')
        super().save_model(request, obj, form, change)
