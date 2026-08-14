

```bash
# 1. Clone du repo
git clone https://github.com/ioi-101/EDUNET_GABON.git
cd EDUNET_GABON

# 2. Création environnement
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configuration .env
cp .env.example .env
# Modifier les infos DB, SECRET_KEY, etc.

# 4. Initialisation
python manage.py migrate_schemas --shared
python manage.py createsuperuser

# 5. Lancer le serveur
python manage.py runserver






# Arrêter PostgreSQL et supprimer le volume
cd /home/president/Github/EDUNET_GABON_BACKEND
docker compose down -v

# Redémarrer PostgreSQL
docker compose up -d

# Supprimer les fichiers de migrations (conserver __init__.py)
find */migrations -name "*.py" ! -name "__init__.py" -delete

# Recréer les migrations
python manage.py makemigrations

# Exécuter les migrations partagées
python manage.py migrate_schemas --shared

# Exécuter les migrations tenant
python manage.py migrate_schemas

# Créer un tenant
python manage.py create_tenant

# Créer le superuser
python manage.py shell


from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context
from tenants.models import Tenant

User = get_user_model()
tenant = Tenant.objects.get(schema_name='civitas')

with schema_context(tenant.schema_name):
    User.objects.create_superuser(
        username='admin',
        email='admin@civitas.com',
        password='admin'
    )