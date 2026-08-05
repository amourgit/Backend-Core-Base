from django.contrib import admin

from .models import EvenementJournal


@admin.register(EvenementJournal)
class EvenementJournalAdmin(admin.ModelAdmin):
    """Le journal d'audit est en lecture seule dans l'admin : sa valeur
    probante repose sur le fait qu'il n'est jamais modifiable a posteriori."""

    list_display = ('action', 'cible_libelle', 'cree_par', 'cree_par_systeme', 'cree_le', 'adresse_ip')
    list_filter = ('action',)
    search_fields = ('cible_libelle', 'cree_par__username', 'cree_par_systeme')
    date_hierarchy = 'cree_le'
    autocomplete_fields = ['cree_par']

    fieldsets = (
        ('Événement', {'fields': ('action', 'cible_libelle', 'entite_type', 'entite_id')}),
        ('Origine', {'fields': ('cree_par', 'cree_par_systeme', 'adresse_ip')}),
        ('Détails', {'fields': ('details',)}),
        ('Horodatage', {'fields': ('cree_le',)}),
    )
    readonly_fields = (
        'action', 'cible_libelle', 'entite_type', 'entite_id',
        'cree_par', 'cree_par_systeme', 'adresse_ip', 'details', 'cree_le',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
