from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class AuditedModel(models.Model):
    """
    Classe abstraite de base qui fournit des champs d'audit tracking.
    Tous les modèles importants devraient hériter de cette classe.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created"
    )
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated"
    )

    class Meta:
        abstract = True  # Ceci est une classe abstraite, ne crée pas de table en DB.