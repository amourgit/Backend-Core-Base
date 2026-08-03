from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import connection
from django.core.management import call_command
from tenants.models import Tenant


# @receiver(post_save, sender=Tenant)
# def create_tenant_schema(sender, instance, created, **kwargs):
#     if created:
#         with connection.cursor() as cursor:
#             # Créer le schéma
#             cursor.execute(f"""
#                 CREATE SCHEMA IF NOT EXISTS {instance.schema_name};
#             """)
            
#             # Définir les permissions
#             cursor.execute(f"""
#                 GRANT ALL ON SCHEMA {instance.schema_name} TO postgres;
#                 GRANT USAGE ON SCHEMA {instance.schema_name} TO postgres;
#             """)
            
#             # Appliquer les migrations dans le nouveau schéma
#             call_command('migrate_schemas', schema_name=instance.schema_name, interactive=False, verbosity=0) 