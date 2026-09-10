# Réforme "identité globale / adhésion tenant" (e72cf35, 9 sept. 2026)
# ANNULÉE : chaque tenant redevient autonome pour ses utilisateurs (voir
# adhesions/management/commands/migrate_users_to_tenant.py pour la
# migration de DONNÉES correspondante -- cette migration-ci ne restaure
# que le SCHÉMA, exact inverse de 0002_remove_user_badges_and_more).
#
# IMPORTANT pour les schémas tenant qui ont déjà subi
# `migrate_users_to_global --drop-local-table` (à ce jour : civitasnews
# uniquement) : cette migration recrée une table `users_user` VIDE.
# `migrate_users_to_tenant` doit tourner APRÈS elle (voir build.sh) pour
# repeupler les comptes depuis `adhesions.MembreTenant` + l'identité
# globale encore présente en schéma public.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('referentiels', '0001_initial'),
        ('users', '0002_remove_user_badges_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Badge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100, unique=True, verbose_name='Nom')),
                ('icone', models.CharField(default='🏅', help_text='Emoji ou code icône court.', max_length=10, verbose_name='Icône')),
                ('description', models.CharField(blank=True, max_length=255, verbose_name='Description')),
            ],
            options={
                'verbose_name': 'Badge',
                'verbose_name_plural': 'Badges',
                'ordering': ['nom'],
            },
        ),
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('etudiant', 'Étudiant'),
                    ('moderateur', 'Modérateur'),
                    ('administrateur', 'Administrateur'),
                    ('organisation', 'Organisation'),
                ],
                db_index=True, default='etudiant', max_length=20, verbose_name='Rôle',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='etablissement',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='utilisateurs', to='referentiels.etablissement', verbose_name='Établissement',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='organisation',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='membres', to='referentiels.organisation', verbose_name='Organisation',
                help_text='Renseigné si le compte représente/gère une organisation publiante.',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='badges',
            field=models.ManyToManyField(blank=True, related_name='utilisateurs', to='users.badge', verbose_name='Badges'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['role'], name='users_user_role_36d76d_idx'),
        ),
    ]
