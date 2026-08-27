# Generated manually — restaure l'intégrité du modèle ReactionNews
# (contrainte d'unicité + utilisateur obligatoire) après le retour en
# arrière de la migration 0003. Voir news/models.py:ReactionNews pour
# le raisonnement complet.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def nettoyer_reactions_incompatibles(apps, schema_editor):
    """Avant de ré-imposer la contrainte d'unicité et le champ
    utilisateur obligatoire, on doit éliminer ce que la fenêtre
    'réactions illimitées' peut avoir laissé en base :
      - réactions anonymes (utilisateur=None) : aucun utilisateur vers
        lequel les rattacher rétroactivement -> supprimées.
      - doublons (news, utilisateur) : on ne garde que la plus récente,
        exactement ce que basculer_reaction aurait produit si le
        toggle n'avait jamais été contourné.
    """
    ReactionNews = apps.get_model('news', 'ReactionNews')

    ReactionNews.objects.filter(utilisateur__isnull=True).delete()

    vus = set()
    # Plus récentes d'abord : la première occurrence rencontrée pour
    # une paire (news, utilisateur) est donc celle qu'on conserve.
    for reaction in ReactionNews.objects.order_by('-cree_le', '-pk'):
        cle = (reaction.news_id, reaction.utilisateur_id)
        if cle in vus:
            reaction.delete()
        else:
            vus.add(cle)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0003_remove_reactionnews_reaction_unique_par_utilisateur_news_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(nettoyer_reactions_incompatibles, noop),
        migrations.AlterField(
            model_name='reactionnews',
            name='utilisateur',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='reactions_news',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Utilisateur',
            ),
        ),
        migrations.AddConstraint(
            model_name='reactionnews',
            constraint=models.UniqueConstraint(fields=('news', 'utilisateur'), name='reaction_unique_par_utilisateur_news'),
        ),
    ]
