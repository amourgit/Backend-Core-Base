from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from common.admin import PublicSchemaOnlyAdminMixin, TenantScopedAdminMixin, DualTenantScopedAdminMixin, SOCLE_FIELDSET_SANS_STATUT
from .models import (
    Tenant,
    TenantInformationsPrimaires,
    TenantDocumentRequis,
    TenantDocumentGenerique,
    TenantTutelle,
)

@admin.register(Tenant)
class TenantAdmin(PublicSchemaOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'schema_name', 'is_active', 'is_public', 'created_at')
    list_filter = ('is_active', 'is_public', 'created_at')
    list_editable = ('is_public',)
    search_fields = ('name', 'schema_name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'schema_name', 'is_active')
        }),
        (_('Visibilité multi-tenant'), {
            'fields': ('is_public',),
            'description': _(
                "Si activé, ce tenant est ajouté automatiquement à la liste "
                "de tenants que le frontend inclut dans CHAQUE requête GET "
                "(en plus du tenant courant de l'utilisateur) — voir "
                "tenants.middleware.TenantMiddleware._fan_out_get. Réservé "
                "aux organisations dont le contenu doit être visible par "
                "tous les usagers, quel que soit leur tenant d'appartenance "
                "(ex: Ministères, Mutuelles)."
            ),
        }),
        (_('Description'), {
            'fields': ('description', 'logo')
        }),
    )


@admin.register(TenantInformationsPrimaires)
class TenantInformationsPrimairesAdmin(TenantScopedAdminMixin):
    """Voir `common.admin.TenantScopedAdminMixin` : visible/éditable
    depuis l'admin global (tous tenants) ET depuis l'admin de CHAQUE
    tenant (limité à sa propre fiche)."""
    list_display = ('tenant', 'raison_sociale', 'statut', 'pourcentage_completion_affiche', 'modifie_le')
    list_filter = ('forme_juridique', 'secteur_activite', 'province')
    search_fields = ('tenant__name', 'raison_sociale', 'sigle', 'numero_rccm', 'numero_nif')
    autocomplete_fields = ('tenant',)
    fieldsets = (
        (None, {'fields': ('tenant', 'statut')}),
        (_('Identification légale'), {
            'fields': (
                ('forme_juridique', 'secteur_activite'),
                ('raison_sociale', 'sigle'),
                ('numero_rccm', 'numero_nif', 'numero_agrement'),
                'date_creation_ou_agrement',
            ),
        }),
        (_('Coordonnées'), {
            'fields': (
                'adresse_siege', ('ville', 'province', 'pays'),
                ('telephone_principal', 'telephone_secondaire'),
                ('email_contact', 'site_web'),
                'reseaux_sociaux',
            ),
        }),
        (_('Responsable légal'), {
            'fields': (
                ('responsable_nom_complet', 'responsable_fonction'),
                ('responsable_telephone', 'responsable_email'),
            ),
        }),
        (_('Contact opérationnel'), {
            'classes': ('collapse',),
            'fields': (
                ('contact_operationnel_nom', 'contact_operationnel_fonction'),
                ('contact_operationnel_telephone', 'contact_operationnel_email'),
            ),
        }),
        (_("Données d'étude"), {
            'fields': ('effectif_estime', 'zone_couverture', 'description_activites'),
        }),
        (_('Vérification plateforme'), {
            'classes': ('collapse',),
            'fields': ('commentaire_verification', ('verifie_par', 'verifie_le')),
        }),
        SOCLE_FIELDSET_SANS_STATUT,
    )

    @admin.display(description=_('Complétion'))
    def pourcentage_completion_affiche(self, obj):
        return f"{obj.pourcentage_completion}%"


@admin.register(TenantDocumentRequis)
class TenantDocumentRequisAdmin(TenantScopedAdminMixin):
    """Voir `common.admin.TenantScopedAdminMixin`."""
    list_display = ('tenant', 'type', 'statut', 'periode_affichee', 'taille_affichee', 'cree_le')
    list_filter = ('type', 'statut')
    search_fields = ('tenant__name', 'nom_fichier_original', 'commentaire_soumission')
    autocomplete_fields = ('tenant',)
    fieldsets = (
        (None, {'fields': ('tenant', 'type', 'statut')}),
        (_('Fichier'), {'fields': ('fichier', 'nom_fichier_original', 'taille', 'type_mime')}),
        (_('Période couverte'), {
            'description': _("Obligatoire pour un type de document PÉRIODIQUE (ex: feuille de route annuelle) — laisser vide pour un document permanent."),
            'fields': ('valide_du', 'valide_au'),
        }),
        (_('Soumission et vérification'), {
            'fields': ('commentaire_soumission', 'motif_rejet', ('verifie_par', 'verifie_le')),
        }),
        SOCLE_FIELDSET_SANS_STATUT,
    )

    @admin.display(description=_('Période'))
    def periode_affichee(self, obj):
        if not obj.valide_du and not obj.valide_au:
            return '—'
        return f"{obj.valide_du or '?'} → {obj.valide_au or '?'}"

    @admin.display(description=_('Taille'))
    def taille_affichee(self, obj):
        return f"{(obj.taille or 0) / (1024 * 1024):.2f} Mo"


@admin.register(TenantDocumentGenerique)
class TenantDocumentGeneriqueAdmin(TenantScopedAdminMixin):
    """Voir `common.admin.TenantScopedAdminMixin`."""
    list_display = ('tenant', 'nom', 'type_libre', 'statut', 'taille_affichee', 'cree_le')
    list_filter = ('statut',)
    search_fields = ('tenant__name', 'nom', 'type_libre', 'description')
    autocomplete_fields = ('tenant',)
    fieldsets = (
        (None, {'fields': ('tenant', 'nom', 'type_libre', 'statut')}),
        (_('Fichier'), {'fields': ('fichier', 'nom_fichier_original', 'taille', 'type_mime')}),
        (_('Description'), {'fields': ('description',)}),
        (_('Période couverte (si document temporaire)'), {'fields': ('valide_du', 'valide_au')}),
        SOCLE_FIELDSET_SANS_STATUT,
    )

    @admin.display(description=_('Taille'))
    def taille_affichee(self, obj):
        return f"{(obj.taille or 0) / (1024 * 1024):.2f} Mo"


@admin.register(TenantTutelle)
class TenantTutelleAdmin(DualTenantScopedAdminMixin):
    """Voir `common.admin.DualTenantScopedAdminMixin` : visible depuis
    l'admin global (toutes relations) et depuis l'admin de CHAQUE tenant
    impliqué (jamais celles concernant deux autres tenants)."""
    list_display = (
        'tenant_sous_tutelle', 'tenant_tutelle', 'type_relation', 'statut',
        'tenant_initiateur', 'valide_par_destinataire_le', 'cree_le',
    )
    list_filter = ('type_relation',)
    search_fields = ('tenant_tutelle__name', 'tenant_sous_tutelle__name', 'intitule', 'reference_juridique')
    autocomplete_fields = ('tenant_tutelle', 'tenant_sous_tutelle', 'tenant_initiateur')
    fieldsets = (
        (None, {'fields': ('tenant_tutelle', 'tenant_sous_tutelle', 'tenant_initiateur', 'statut')}),
        (_('Nature de la relation'), {
            'fields': ('type_relation', 'intitule', 'description', 'reference_juridique'),
        }),
        (_('Période'), {'fields': ('date_effet', 'date_fin')}),
        (_('Consentement'), {
            'fields': ('initiateur_a_valide_le', 'valide_par_destinataire_le', 'motif_refus', 'motif_rupture'),
        }),
        SOCLE_FIELDSET_SANS_STATUT,
    )

