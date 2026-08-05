from django.contrib import admin

from common.admin import TracabiliteAdminMixin, SOCLE_FIELDSET
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(TracabiliteAdminMixin, admin.ModelAdmin):
    list_display = ('titre', 'destinataire', 'format', 'lu', 'urgente', 'category_tab', 'cree_le')
    list_filter = ('format', 'lu', 'urgente', 'category_tab')
    search_fields = ('titre', 'description', 'destinataire__username')
    autocomplete_fields = ['destinataire']
    date_hierarchy = 'cree_le'

    fieldsets = (
        ('Destinataire', {'fields': ('destinataire',)}),
        ('Contenu', {'fields': ('format', 'titre', 'description', 'lien', 'notice')}),
        ('Catégorie (affichage frontend)', {
            'fields': ('categorie_nom', 'categorie_couleur', 'categorie_icone'),
        }),
        ('Classement', {'fields': ('category_tab', 'tag', 'urgente')}),
        ('État', {'fields': ('lu',)}),
        ('Actions interactives', {
            'classes': ('collapse',),
            'description': "Boutons d'action affichés sous la notification côté frontend (JSON).",
            'fields': ('actions',),
        }),
        SOCLE_FIELDSET,
    )
