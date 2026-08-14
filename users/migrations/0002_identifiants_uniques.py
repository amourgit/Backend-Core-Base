from django.db import migrations, models


def normaliser_champs_identifiants_vides(apps, schema_editor):
    """Convertit les chaînes vides ('') d'email/phone_number en NULL.

    Nécessaire AVANT d'ajouter unique=True sur ces deux champs : plusieurs
    utilisateurs existants partagent aujourd'hui la même valeur '' (champ
    non renseigné), ce qui ferait échouer immédiatement la création de
    l'index unique tant que ces valeurs restent des chaînes vides
    identiques entre elles. NULL, lui, n'entre jamais en collision avec
    un autre NULL sous une contrainte unique standard (PostgreSQL traite
    chaque NULL comme distinct des autres).
    """
    User = apps.get_model('users', 'User')
    User.objects.filter(email='').update(email=None)
    User.objects.filter(phone_number='').update(phone_number=None)


def revenir_aux_chaines_vides(apps, schema_editor):
    """Sens inverse, pour permettre un migrate en arrière (reverse)."""
    User = apps.get_model('users', 'User')
    User.objects.filter(email__isnull=True).update(email='')
    User.objects.filter(phone_number__isnull=True).update(phone_number='')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        # 1. Nettoyage des données existantes -- DOIT précéder l'ajout des
        #    contraintes unique ci-dessous, sinon l'ALTER TABLE échoue avec
        #    une IntegrityError sur la première paire de doublons ''.
        migrations.RunPython(
            normaliser_champs_identifiants_vides,
            revenir_aux_chaines_vides,
        ),
        # 2. email et phone_number deviennent les deux identifiants de
        #    connexion possibles (voir UsersService.get_user_by_identifiant)
        #    -- doivent donc être uniques. null=True (plutôt qu'un défaut
        #    '' partagé) pour que "non renseigné" ne bloque jamais la
        #    création d'un second compte sans email/téléphone.
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(
                blank=True, max_length=254, null=True, unique=True,
                verbose_name='email address',
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='phone_number',
            field=models.CharField(
                blank=True, max_length=20, null=True, unique=True,
                verbose_name='Phone number',
            ),
        ),
    ]
