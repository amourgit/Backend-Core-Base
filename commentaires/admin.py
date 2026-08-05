from django.contrib import admin

from common.admin import TracabiliteAdminMixin, SOCLE_FIELDSET
from .models import Commentaire, MediaJointCommentaire, ReactionCommentaire, VoteCommentaire


class MediaJointInline(admin.TabularInline):
    model = MediaJointCommentaire
    extra = 0
    fields = ('type', 'fichier', 'url_externe')


@admin.register(Commentaire)
class CommentaireAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('apercu_contenu', 'news', 'auteur', 'type_contenu', 'est_epingle', 'est_reponse_acceptee', 'cree_le')
    list_filter = ('type_contenu', 'est_epingle', 'est_reponse_acceptee')
    search_fields = ('contenu', 'auteur__username', 'news__titre')
    autocomplete_fields = ['news', 'auteur', 'reponse_a', 'mentions']
    inlines = [MediaJointInline]
    date_hierarchy = 'cree_le'

    fieldsets = (
        ('Rattachement', {
            'description': "News commentée et, le cas échéant, commentaire parent (fil de réponses).",
            'fields': ('news', 'reponse_a'),
        }),
        ('Auteur', {'fields': ('auteur',)}),
        ('Contenu', {'fields': ('type_contenu', 'contenu', 'audio_fichier', 'audio_duration', 'mentions')}),
        ('Modération', {'fields': ('est_epingle', 'est_reponse_acceptee')}),
        SOCLE_FIELDSET,
    )

    @admin.display(description='Contenu')
    def apercu_contenu(self, obj):
        return (obj.contenu[:60] + '…') if len(obj.contenu) > 60 else obj.contenu


@admin.register(ReactionCommentaire)
class ReactionCommentaireAdmin(admin.ModelAdmin):
    list_display = ('commentaire', 'utilisateur', 'type_reaction', 'cree_le')
    search_fields = ('utilisateur__username',)
    autocomplete_fields = ['commentaire', 'utilisateur']


@admin.register(VoteCommentaire)
class VoteCommentaireAdmin(admin.ModelAdmin):
    list_display = ('commentaire', 'utilisateur', 'direction', 'cree_le')
    list_filter = ('direction',)
    autocomplete_fields = ['commentaire', 'utilisateur']
