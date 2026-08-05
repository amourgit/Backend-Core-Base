from django.contrib import admin

from common.admin import TracabiliteAdminMixin, SOCLE_FIELDSET, SOCLE_READONLY_FIELDS
from .models import LienPublication, LienAcces


class LienAccesInline(admin.TabularInline):
    model = LienAcces
    extra = 0
    fields = ('type_acces', 'horodatage', 'adresse_ip')
    readonly_fields = ('type_acces', 'horodatage', 'adresse_ip')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LienPublication)
class LienPublicationAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('news', 'code_court', 'visibilite', 'usage_unique', 'expiration', 'nb_clics', 'nb_scans', 'cree_le')
    list_filter = ('visibilite', 'usage_unique')
    search_fields = ('code_court', 'news__titre')
    autocomplete_fields = ['news']
    inlines = [LienAccesInline]

    fieldsets = (
        ('Rattachement', {'fields': ('news', 'url_publique', 'code_court', 'qr_code')}),
        ('Contrôle d\u2019accès', {
            'description': "Règles de visibilité et de protection du lien partagé.",
            'fields': ('visibilite', 'mot_de_passe_hash', 'expiration', 'usage_unique', 'deja_utilise'),
        }),
        ('Portée de diffusion ciblée', {
            'classes': ('collapse',),
            'description': "Audience visée par ce lien (à titre indicatif, texte libre).",
            'fields': (
                ('scope_etablissement', 'scope_province'),
                ('scope_promotion', 'scope_organisation', 'scope_classe'),
            ),
        }),
        SOCLE_FIELDSET,
    )
    readonly_fields = SOCLE_READONLY_FIELDS + ('code_court', 'deja_utilise')

    @admin.display(description='Clics')
    def nb_clics(self, obj):
        return obj.acces.filter(type_acces=LienAcces.TypeAcces.CLIC).count()

    @admin.display(description='Scans')
    def nb_scans(self, obj):
        return obj.acces.filter(type_acces=LienAcces.TypeAcces.SCAN).count()


@admin.register(LienAcces)
class LienAccesAdmin(admin.ModelAdmin):
    list_display = ('lien', 'type_acces', 'horodatage', 'adresse_ip')
    list_filter = ('type_acces',)
    search_fields = ('lien__code_court',)
    autocomplete_fields = ['lien']
    date_hierarchy = 'horodatage'

    def has_add_permission(self, request):
        return False
