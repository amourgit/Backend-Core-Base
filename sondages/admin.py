from django.contrib import admin

from common.admin import TracabiliteAdminMixin, SOCLE_FIELDSET_SANS_STATUT
from .models import Sondage, ChoixSondage, VoteSondage


class ChoixSondageInline(admin.TabularInline):
    model = ChoixSondage
    extra = 2
    fields = ('libelle', 'image', 'ordre')


@admin.register(Sondage)
class SondageAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('titre', 'news', 'statut', 'type_vote', 'date_debut', 'date_fin')
    list_filter = ('type_vote', 'anonymat', 'visibilite_resultat')
    search_fields = ('titre', 'question', 'news__titre')
    autocomplete_fields = ['news']
    inlines = [ChoixSondageInline]
    date_hierarchy = 'date_debut'

    fieldsets = (
        ('Rattachement', {'fields': ('news',)}),
        ('Contenu', {'fields': ('titre', 'description', 'question', 'image')}),
        ('Fenêtre de vote', {'fields': ('date_debut', 'date_fin')}),
        ('Règles de vote', {'fields': ('type_vote', 'anonymat', 'visibilite_resultat')}),
        ('Publication', {'fields': ('statut',)}),
        SOCLE_FIELDSET_SANS_STATUT,
    )


@admin.register(ChoixSondage)
class ChoixSondageAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'sondage', 'ordre', 'cree_le')
    search_fields = ('libelle', 'sondage__titre')
    autocomplete_fields = ['sondage']
    readonly_fields = ('cree_le',)


@admin.register(VoteSondage)
class VoteSondageAdmin(admin.ModelAdmin):
    list_display = ('sondage', 'choix', 'utilisateur', 'cree_le')
    search_fields = ('sondage__titre', 'utilisateur__username')
    autocomplete_fields = ['sondage', 'choix', 'utilisateur']
