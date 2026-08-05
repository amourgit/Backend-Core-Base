"""
commentaires/signals.py
==========================

Découple `commentaires` de `notifications` au moment de l'écriture du
code (import différé dans le handler) tout en gardant le déclenchement
automatique : dès qu'un commentaire est créé, les notifications
pertinentes partent sans que la vue n'ait à s'en soucier.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Commentaire


@receiver(post_save, sender=Commentaire)
def notifier_apres_creation_commentaire(sender, instance: Commentaire, created, **kwargs):
    if not created:
        return

    from notifications.api.v1 import services as notifications_services

    notifications_services.notifier_nouveau_commentaire(instance)
    notifications_services.notifier_reponse_commentaire(instance)
    # Note : les mentions (M2M) ne sont pas encore renseignées à ce stade
    # (elles sont fixées juste après le save() dans la vue) — voir
    # CommentaireViewSet.perform_create qui déclenche explicitement
    # notifier_mention() une fois `mentions.set(...)` effectué.
