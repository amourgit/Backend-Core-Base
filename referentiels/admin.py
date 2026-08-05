from django.contrib import admin
from django.utils.html import format_html

from common.admin import TracabiliteAdminMixin, SOCLE_FIELDSET
from .models import Categorie, Organisation, Etablissement


@admin.register(Categorie)
class CategorieAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('nom', 'pastille_couleur', 'icone', 'statut')
    search_fields = ('nom', 'description')
    fieldsets = (
        ('Identification', {'fields': ('nom', 'description')}),
        ('Apparence (frontend)', {'fields': ('couleur', 'icone')}),
        SOCLE_FIELDSET,
    )

    @admin.display(description='Couleur')
    def pastille_couleur(self, obj):
        return format_html(
            '<span style="display:inline-block;width:14px;height:14px;border-radius:50%;'
            'background:{};margin-right:6px;vertical-align:middle;"></span>{}',
            obj.couleur, obj.couleur,
        )


@admin.register(Organisation)
class OrganisationAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('nom', 'type', 'statut', 'cree_le')
    list_filter = ('type',)
    search_fields = ('nom', 'description')
    fieldsets = (
        ('Identification', {'fields': ('nom', 'type', 'logo')}),
        ('Description', {'fields': ('description',)}),
        SOCLE_FIELDSET,
    )


@admin.register(Etablissement)
class EtablissementAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('nom', 'province', 'statut')
    list_filter = ('province',)
    search_fields = ('nom', 'province')
    fieldsets = (
        ('Identification', {'fields': ('nom', 'province')}),
        SOCLE_FIELDSET,
    )
