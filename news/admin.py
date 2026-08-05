from django.contrib import admin

from common.admin import TracabiliteAdminMixin, SOCLE_FIELDSET_SANS_STATUT
from .models import News, NewsVue, ReactionNews, NewsMedia, NewsImageGalerie, DocumentJoint, Tag


class NewsMediaInline(admin.TabularInline):
    model = NewsMedia
    extra = 0
    fields = ('type', 'fichier', 'url_externe', 'vignette', 'titre', 'description', 'duree', 'ordre')


class NewsImageGalerieInline(admin.TabularInline):
    model = NewsImageGalerie
    extra = 0
    fields = ('image', 'legende', 'ordre')


class DocumentJointInline(admin.TabularInline):
    model = DocumentJoint
    extra = 0
    fields = ('nom', 'fichier', 'type', 'taille')
    readonly_fields = ('taille',)


@admin.register(News)
class NewsAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('titre', 'type', 'statut', 'visibilite', 'auteur', 'categorie', 'province', 'cree_le')
    list_filter = ('visibilite', 'type', 'categorie', 'province')
    search_fields = ('titre', 'description', 'slug', 'auteur__username')
    prepopulated_fields = {'slug': ('titre',)}
    autocomplete_fields = ['auteur', 'organisation', 'etablissement', 'categorie', 'tags']
    inlines = [NewsMediaInline, NewsImageGalerieInline, DocumentJointInline]
    date_hierarchy = 'cree_le'

    fieldsets = (
        ('Identification', {
            'description': "Titre, résumé et identifiant public (slug) de la publication.",
            'fields': ('titre', 'slug', 'type', 'description'),
        }),
        ('Contenu', {'fields': ('contenu', 'image')}),
        ('Classification', {
            'description': "Catégorisation utilisée pour le filtrage et les statistiques côté frontend.",
            'fields': ('categorie', 'tags', 'province', 'lieu'),
        }),
        ('Auteur & Organisation', {'fields': ('auteur', 'organisation', 'etablissement')}),
        ('Programmation (événements)', {
            'classes': ('collapse',),
            'fields': ('date_debut', 'date_fin'),
        }),
        ('Publication', {'fields': ('statut', 'visibilite')}),
        ('Compteurs', {'classes': ('collapse',), 'fields': ('partages',)}),
        SOCLE_FIELDSET_SANS_STATUT,
    )


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('nom',)
    search_fields = ('nom',)


@admin.register(ReactionNews)
class ReactionNewsAdmin(admin.ModelAdmin):
    list_display = ('news', 'utilisateur', 'type_reaction', 'cree_le')
    list_filter = ('type_reaction',)
    search_fields = ('news__titre', 'utilisateur__username')
    autocomplete_fields = ['news', 'utilisateur']


@admin.register(NewsVue)
class NewsVueAdmin(admin.ModelAdmin):
    list_display = ('news', 'utilisateur', 'horodatage', 'adresse_ip')
    date_hierarchy = 'horodatage'
    search_fields = ('news__titre',)
    autocomplete_fields = ['news', 'utilisateur']

    def has_add_permission(self, request):
        return False  # table de faits générée par l'API, pas de saisie manuelle
