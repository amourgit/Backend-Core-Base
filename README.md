Bon projet!
# 🏛️ Projet de Réseau Éducatif Gabonais – Backend Multitenant (Django/PostgreSQL)

## 🧭 Présentation Générale

Ce projet est l’implémentation back-end du **système éducatif numérique national du Gabon**, visant à connecter l’ensemble des universités, écoles et instituts à travers une **infrastructure sécurisée, moderne et modulaire**.

Il repose sur une architecture **multi-tenant** (chaque établissement = un tenant isolé), un système de gestion **d’intranet personnalisé**, avec une communication centralisée vers un **hub national de sécurité et de services éducatifs**.

---

## 🧱 Objectifs du Projet

- ✅ Offrir un **système éducatif numérique unifié** à l’échelle nationale.
- ✅ Garantir l’**autonomie locale** de chaque établissement tout en assurant la **supervision centralisée**.
- ✅ Fournir un système **multi-tenant robuste**, sécurisé, et extensible.
- ✅ Supporter la **connexion distante** des interfaces front-end, via API sécurisée.
- ✅ Favoriser l’usage de **logiciels libres** et de technologies open source.

---

## ⚙️ Stack Technologique

| Technologie | Rôle |
|-------------|------|
| **Django** | Framework backend principal |
| **PostgreSQL** | Base de données relationnelle, avec schéma par tenant |
| **django-tenants** ou **django-tenant-schemas** | Gestion multitenant avec schémas séparés |
| **SimpleJWT (ou Django REST Framework JWT)** | Authentification sécurisée par tokens |
| **Django REST Framework (DRF)** | API RESTful pour les frontends Angular/React |
| **Docker (optionnel)** | Conteneurisation et orchestration |
| **Nginx / Gunicorn** | Déploiement en production |
| **Celery / Redis** | Tâches asynchrones (si besoin) |

---

## 🧩 Fonctionnalités Clés

### 🔐 Multitenancy par schéma PostgreSQL

- Chaque établissement dispose de :
  - Son propre schéma PostgreSQL isolé
  - Ses propres tables (utilisateurs, cours, notes, etc.)
  - Son propre sous-domaine ou identifiant (ex : `univ-libreville.monprojet.edu`)

- Un **schéma public** contient les données communes :
  - Utilisateurs super-admins
  - Configuration générale
  - Journalisation inter-tenant

### 🔑 Authentification & sécurité

- Connexion via **JWT Token** pour toutes les API sécurisées
- Génération de tokens pour :
  - Interfaces utilisateurs (students/admins)
  - Interfaces machine ↔ machine (applications front, intranet web)
- Système de permissions par rôle :
  - SuperAdmin, Admin local, Enseignant, Étudiant

### 🛠️ Modules principaux

| Module | Description |
|--------|-------------|
| **Comptes & Auth** | Création de tenants, gestion des utilisateurs, rôles |
| **Intranet** | Accès à l’interface éducative locale : cours, notes, documents |
| **Gestion Académique** | Filières, classes, étudiants, enseignants, emplois du temps |
| **Demandes administratives** | Actes, certificats, relevés de notes automatisés |
| **Messagerie** | Système de discussion intra-établissement |
| **Suivi & journalisation** | Logs d’activité, audit de sécurité |
| **Connexion au centre** | Synchronisation de données, centralisation analytique |

---

## 🌐 API REST

- API REST conforme aux standards modernes :
  - Auth via `/api/token/`, `/api/token/refresh/`
  - Routes modulaires pour chaque service :
    - `/api/courses/`, `/api/students/`, `/api/requests/`, etc.
- Gestion **multitenant transparente** via sous-domaines ou header de contexte (`X-Tenant-ID`)
- **Rate limiting**, CORS, sécurité CSRF désactivée pour les connexions API tokenisées

---

## 🔄 Connexion avec les Frontends

- Le backend est **découplé** des interfaces :
  - Angular, React, ou App mobile peuvent se connecter via **API sécurisées**
- Pour chaque frontend, un **token temporaire ou permanent** peut être généré
- Support des connexions HTTP, HTTPS, et socket (si besoin de messagerie temps réel)

---

## 🧑‍💼 Utilisateurs & rôles

| Rôle | Accès |
|------|-------|
| SuperAdmin | Gère tous les tenants, configure la plateforme globale |
| Admin Établissement | Gère uniquement son tenant : étudiants, enseignants, modules |
| Enseignant | Ajoute des cours, suit les notes, échange avec les étudiants |
| Étudiant | Accède à ses ressources pédagogiques et administratives |

---

## 🧪 Tests et validation

- Utilisation de `pytest` ou `unittest` pour les tests :
  - Authentification
  - Isolation des tenants
  - Permissions
- Test de **scalabilité** : création et gestion de 50+ tenants simulés
- Monitoring avec Prometheus + Grafana (optionnel)

---

## 🚀 Déploiement (résumé rapide)

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
tenant = Tenant.objects.get(schema_name='civitas-news')

with schema_context(tenant.schema_name):
    User.objects.create_superuser(
        username='admin',
        email='admin@civitas-news.com',
        password='admin'
    )