from django.contrib import admin

from common.admin import TracabiliteAdminMixin, SOCLE_FIELDSET_SANS_STATUT
from .models import Signalement


@admin.register(Signalement)
class SignalementAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('titre_ou_apercu', 'type_contenu', 'motif', 'statut', 'auteur_signalement', 'cree_le')
    list_filter = ('motif', 'type_contenu')
    search_fields = ('titre_ou_apercu', 'description', 'auteur_signalement__username')
    autocomplete_fields = ['auteur_signalement']
    date_hierarchy = 'cree_le'

    fieldsets = (
        ('Contenu signalé', {'fields': ('type_contenu', 'contenu_id', 'titre_ou_apercu')}),
        ('Signalement', {'fields': ('motif', 'description', 'auteur_signalement')}),
        ('Traitement', {'fields': ('statut',)}),
        SOCLE_FIELDSET_SANS_STATUT,
    )
