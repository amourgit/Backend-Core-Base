"""
notifications/api/v1/services.py
===================================

Point d'entrée unique pour créer une notification depuis N'IMPORTE
QUELLE autre app (news, commentaires, sondages...) sans dupliquer la
logique de construction. C'est ici que vivent les "traitements déjà
tout faits" : dès qu'un événement pertinent se produit ailleurs dans
la plateforme, il suffit d'appeler `creer_notification(...)`.
"""

from ... import models


def creer_notification(
    destinataire,
    format: str,
    titre: str,
    description: str = '',
    categorie_nom: str = 'Général',
    categorie_couleur: str = '#5B4DFF',
    categorie_icone: str = '',
    lien: str = '',
    tag: str = '',
    urgente: bool = False,
    category_tab: str = models.CategoryTab.ALL,
    notice: str = '',
    actions: list = None,
) -> models.Notification:
    return models.Notification.objects.create(
        destinataire=destinataire,
        format=format,
        titre=titre,
        description=description,
        categorie_nom=categorie_nom,
        categorie_couleur=categorie_couleur,
        categorie_icone=categorie_icone,
        lien=lien,
        tag=tag,
        urgente=urgente,
        category_tab=category_tab,
        notice=notice,
        actions=actions or [],
    )


def notifier_nouveau_commentaire(commentaire) -> None:
    """Notifie l'auteur de la News (sauf s'il commente lui-même) qu'un
    nouveau commentaire vient d'être publié."""
    news = commentaire.news
    if news.auteur_id == commentaire.auteur_id:
        return
    creer_notification(
        destinataire=news.auteur,
        format=models.NotificationFormat.ACTUALITE,
        titre='Nouveau commentaire',
        description=f'{commentaire.auteur.get_full_name()} a commenté « {news.titre} ».',
        categorie_nom='Commentaires', categorie_couleur='#3B82F6', categorie_icone='MessageSquare',
        lien=f'/news?news={news.slug}', category_tab=models.CategoryTab.DIRECT,
    )


def notifier_reponse_commentaire(commentaire) -> None:
    """Notifie l'auteur du commentaire parent qu'on lui a répondu."""
    parent = commentaire.reponse_a
    if not parent or parent.auteur_id == commentaire.auteur_id:
        return
    creer_notification(
        destinataire=parent.auteur,
        format=models.NotificationFormat.ACTUALITE,
        titre='Nouvelle réponse',
        description=f'{commentaire.auteur.get_full_name()} a répondu à votre commentaire.',
        categorie_nom='Réponses', categorie_couleur='#8B5CF6', categorie_icone='CornerUpLeft',
        lien=f'/news?news={commentaire.news.slug}', category_tab=models.CategoryTab.DIRECT,
    )


def notifier_mention(commentaire, utilisateur_mentionne) -> None:
    creer_notification(
        destinataire=utilisateur_mentionne,
        format=models.NotificationFormat.ACTUALITE,
        titre='Vous avez été mentionné',
        description=f'{commentaire.auteur.get_full_name()} vous a mentionné dans un commentaire.',
        categorie_nom='Mentions', categorie_couleur='#EC4899', categorie_icone='AtSign',
        lien=f'/news?news={commentaire.news.slug}', category_tab=models.CategoryTab.DIRECT,
    )
