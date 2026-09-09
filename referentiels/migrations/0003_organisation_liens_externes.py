# Generated manually (cohérent avec le style des migrations existantes de cette app)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referentiels', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='organisation',
            name='site_web',
            field=models.URLField(
                blank=True, max_length=300,
                help_text="Lien externe principal de l'organisation, affiché sur sa carte d'identité (news card).",
                verbose_name='Site web',
            ),
        ),
        migrations.AddField(
            model_name='organisation',
            name='reseaux_sociaux',
            field=models.JSONField(
                blank=True, default=dict,
                help_text=(
                    "Dictionnaire libre {plateforme: url}, ex: "
                    "{'facebook': 'https://...', 'instagram': 'https://...', 'twitter': 'https://...', "
                    "'linkedin': 'https://...', 'youtube': 'https://...', 'whatsapp': 'https://...'}. "
                    "Clés non contraintes côté modèle : le frontend affiche uniquement les plateformes "
                    "reconnues (voir ORGANISATION_SOCIAL_ICONS côté frontend) et ignore le reste."
                ),
                verbose_name='Réseaux sociaux',
            ),
        ),
    ]
