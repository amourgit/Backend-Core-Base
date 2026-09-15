"""
Mixins d'administration communs — appliqués par tous les `admin.py`
des apps métier pour exposer le Socle de Traçabilité de façon uniforme.
"""

from django.contrib import admin
from django.db import connection, models
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name


def est_schema_public():
    """True si la connexion active est sur le schéma PUBLIC (admin
    global de plateforme). Utilitaire partagé par `PublicSchemaOnlyAdminMixin`
    et `TenantScopedAdminMixin` ci-dessous, ainsi que par
    `tenants/api/v1/mixins.py` (SharedTenantScopedModelViewSet) côté API —
    même vérification, un seul endroit."""
    return connection.schema_name == get_public_schema_name()


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
        return est_schema_public()

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


class TenantScopedAdminMixin(admin.ModelAdmin):
    """
    Mixin d'admin pour un modèle SHARED_APPS (une seule copie en schéma
    public) dont chaque ligne appartient à UN tenant précis (champ
    `tenant`), et qui doit rester éditable en LIBRE-SERVICE depuis
    l'admin de CE tenant — contrairement à `Tenant`/`Domain` eux-mêmes
    (voir `PublicSchemaOnlyAdminMixin` ci-dessus, qui ferme complètement
    l'accès tenant). Utilisé par `tenants.admin` pour
    `TenantInformationsPrimaires`/`TenantDocumentRequis`/
    `TenantDocumentGenerique`.

    Comportement :
      - Depuis le schéma PUBLIC (admin global, superuser) : aucune
        restriction — toutes les lignes, tous tenants confondus,
        visibles/éditables (utile à la vérification et à l'étude
        transverse des données d'identité par la plateforme).
      - Depuis un schéma TENANT : le queryset est filtré sur le tenant
        courant (résolu via `connection.schema_name`, PAS via
        `request.tenant` qui n'existe qu'en contexte DRF) — un
        administrateur de tenant ne voit et ne modifie QUE les lignes de
        SON PROPRE tenant, jamais celles d'un autre (fuite fermée,
        contrairement à ce que le search_path django-tenants
        permettrait par défaut sur un ModelAdmin non protégé). Le champ
        `tenant` est alors automatiquement renseigné et lecture seule
        (impossible de créer/modifier la fiche d'un AUTRE tenant en
        trafiquant le formulaire).
      - `cree_par`/`modifie_par` ne sont renseignés que depuis le schéma
        public — voir la note détaillée en tête de
        `tenants/models.py` (section "Informations d'identité...") sur
        pourquoi cette FK est invalide pour un administrateur de tenant ;
        on utilise alors `cree_par_systeme`/`modifie_par_systeme`.

    Volontairement indépendant de `TracabiliteAdminMixin` (pas de
    composition par héritage multiple) : ce dernier assigne
    `cree_par`/`modifie_par` = `request.user` sans condition, ce qui est
    précisément le comportement à éviter ici.
    """

    readonly_fields = SOCLE_READONLY_FIELDS

    def get_list_filter(self, request):
        return tuple(self.list_filter) + ('statut', 'origine_donnee')

    def _tenant_courant(self, request):
        if est_schema_public():
            return None
        from tenants.models import Tenant
        return Tenant.objects.filter(schema_name=connection.schema_name).first()

    def _identifiant_acteur(self, request):
        utilisateur = request.user
        nom = utilisateur.get_username() if hasattr(utilisateur, 'get_username') else str(utilisateur)
        return f"tenant:{connection.schema_name}:{nom or utilisateur.pk}"

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)

    def _objet_visible(self, request, obj):
        if est_schema_public():
            return True
        tenant = self._tenant_courant(request)
        return tenant is not None and obj.tenant_id == tenant.id

    def has_view_permission(self, request, obj=None):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return False
        return True if obj is None else self._objet_visible(request, obj)

    def has_add_permission(self, request):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Jamais de suppression physique (Socle de Traçabilité) : le
        # bouton "Supprimer" de l'admin est désactivé pour tout le monde,
        # y compris l'admin global — utiliser `supprimer_logiquement()`.
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if est_schema_public():
            return qs
        tenant = self._tenant_courant(request)
        return qs.filter(tenant=tenant) if tenant else qs.none()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        tenant = self._tenant_courant(request)
        if tenant is not None and 'tenant' in form.base_fields:
            form.base_fields['tenant'].disabled = True
            form.base_fields['tenant'].initial = tenant.pk
        return form

    def save_model(self, request, obj, form, change):
        tenant = self._tenant_courant(request)
        if tenant is not None:
            # Verrouille le tenant côté serveur, indépendamment de ce que
            # le formulaire désactivé aurait pu recevoir côté client.
            obj.tenant = tenant
        if not change:
            if est_schema_public():
                obj.cree_par = request.user
            else:
                obj.cree_par_systeme = self._identifiant_acteur(request)
        else:
            if est_schema_public():
                obj.modifie_par = request.user
            else:
                obj.modifie_par_systeme = self._identifiant_acteur(request)
            if not obj.motif_derniere_modification:
                obj.motif_derniere_modification = _('Modification via l’interface d’administration')
        super().save_model(request, obj, form, change)


class DualTenantScopedAdminMixin(admin.ModelAdmin):
    """
    Variante de `TenantScopedAdminMixin` ci-dessus pour un modèle
    SHARED_APPS qui relie DEUX tenants (ex: `tenants.TenantTutelle` :
    `tenant_tutelle` / `tenant_sous_tutelle`) plutôt qu'un seul champ
    `tenant`. Mêmes garanties :
      - Admin global (schéma public) : aucune restriction.
      - Admin d'un tenant : ne voit/ne modifie que les lignes où SON
        PROPRE tenant apparaît dans L'UN OU L'AUTRE des champs listés
        dans `champs_tenant` (par défaut `('tenant_tutelle',
        'tenant_sous_tutelle')`) — jamais une ligne concernant deux
        AUTRES tenants.
      - Traçabilité sûre du point de vue schéma, comme
        `TenantScopedAdminMixin` (voir la note d'architecture en tête
        de tenants/models.py).

    Contrairement à `TenantScopedAdminMixin`, ne verrouille pas de champ
    tenant en écriture ni n'autorise la création depuis un admin de
    tenant : une tutelle engage TOUJOURS un tenant tiers et suit un
    workflow de double consentement (voir `TenantTutelle.valider`/
    `refuser`/`rompre`) géré par l'API, pas par un formulaire d'admin
    qui court-circuiterait l'accord de l'autre partie.
    """
    champs_tenant = ('tenant_tutelle', 'tenant_sous_tutelle')
    readonly_fields = SOCLE_READONLY_FIELDS

    def get_list_filter(self, request):
        return tuple(self.list_filter) + ('statut', 'origine_donnee')

    def _tenant_courant(self, request):
        if est_schema_public():
            return None
        from tenants.models import Tenant
        return Tenant.objects.filter(schema_name=connection.schema_name).first()

    def _identifiant_acteur(self, request):
        utilisateur = request.user
        nom = utilisateur.get_username() if hasattr(utilisateur, 'get_username') else str(utilisateur)
        return f"tenant:{connection.schema_name}:{nom or utilisateur.pk}"

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)

    def _objet_visible(self, request, obj):
        if est_schema_public():
            return True
        tenant = self._tenant_courant(request)
        if tenant is None:
            return False
        return any(getattr(obj, f'{champ}_id') == tenant.id for champ in self.champs_tenant)

    def has_view_permission(self, request, obj=None):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return False
        return True if obj is None else self._objet_visible(request, obj)

    def has_add_permission(self, request):
        # Rattrapage manuel possible depuis l'admin global uniquement --
        # jamais depuis un admin de tenant (contournerait le
        # consentement de l'autre partie, voir le docstring ci-dessus).
        return est_schema_public() and bool(request.user and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if est_schema_public():
            return qs
        tenant = self._tenant_courant(request)
        if not tenant:
            return qs.none()
        filtre = models.Q()
        for champ in self.champs_tenant:
            filtre |= models.Q(**{champ: tenant})
        return qs.filter(filtre)

    def save_model(self, request, obj, form, change):
        if not change:
            if est_schema_public():
                obj.cree_par = request.user
            else:
                obj.cree_par_systeme = self._identifiant_acteur(request)
        else:
            if est_schema_public():
                obj.modifie_par = request.user
            else:
                obj.modifie_par_systeme = self._identifiant_acteur(request)
            if not obj.motif_derniere_modification:
                obj.motif_derniere_modification = _('Modification via l’interface d’administration')
        super().save_model(request, obj, form, change)
