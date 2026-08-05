"""
commentaires/api/v1/services.py
==================================
"""

from ... import models


def basculer_vote(commentaire: models.Commentaire, utilisateur, direction: str) -> models.Commentaire:
    existant = models.VoteCommentaire.objects.filter(commentaire=commentaire, utilisateur=utilisateur).first()

    if existant and existant.direction == direction:
        existant.delete()
    elif existant:
        existant.direction = direction
        existant.save(update_fields=['direction'])
    else:
        models.VoteCommentaire.objects.create(commentaire=commentaire, utilisateur=utilisateur, direction=direction)

    return commentaire


def basculer_reaction(commentaire: models.Commentaire, utilisateur, type_reaction: str) -> models.Commentaire:
    existante = models.ReactionCommentaire.objects.filter(
        commentaire=commentaire, utilisateur=utilisateur, type_reaction=type_reaction,
    ).first()
    if existante:
        existante.delete()
    else:
        models.ReactionCommentaire.objects.create(commentaire=commentaire, utilisateur=utilisateur, type_reaction=type_reaction)
    return commentaire


def extraire_mentions(contenu: str):
    """Extrait les `@username` du contenu d'un commentaire pour peupler
    la relation `mentions` et déclencher les notifications associées."""
    import re
    from django.contrib.auth import get_user_model

    User = get_user_model()
    usernames = set(re.findall(r'@(\w+)', contenu or ''))
    if not usernames:
        return []
    return list(User.objects.filter(username__in=usernames))
