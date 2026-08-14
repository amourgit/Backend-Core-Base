"""
Script de chargement des données de test pour CIVITAS NEWS
Charge les données depuis fixtures/sample_data.json via Django ORM
"""

import os
import sys
import json
from datetime import datetime
from django.utils import timezone

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context, tenant_context
from news.models import News, Tag, NewsVue, ReactionNews, NewsMedia, NewsImageGalerie, DocumentJoint, NewsType, NewsStatutChoices, Visibilite, Province, TypeReaction
from commentaires.models import Commentaire, MediaJointCommentaire, ReactionCommentaire, VoteCommentaire, TypeContenuCommentaire
from sondages.models import Sondage, ChoixSondage, VoteSondage, TypeVoteSondage, VisibiliteResultatSondage, SondageStatutChoices
from referentiels.models import Categorie, Etablissement, Organisation
from tenants.models import Tenant

User = get_user_model()

def load_json_data(filepath):
    """Charge les données depuis le fichier JSON"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_first_user():
    """Récupère le premier utilisateur de la base"""
    user = User.objects.first()
    if not user:
        raise ValueError("Aucun utilisateur trouvé dans la base de données. Veuillez d'abord créer un utilisateur.")
    return user

def get_tenant():
    """Récupère le premier tenant de la base"""
    tenant = Tenant.objects.first()
    if not tenant:
        raise ValueError("Aucun tenant trouvé dans la base de données. Veuillez d'abord créer un tenant.")
    return tenant

def create_categories(data):
    """Crée les catégories"""
    print("Création des catégories...")
    categories_map = {}
    for cat_data in data.get('categories', []):
        cat, created = Categorie.objects.get_or_create(
            nom=cat_data['nom'],
            defaults={
                'couleur': cat_data.get('couleur', '#5B4DFF'),
                'icone': cat_data.get('icone', 'Newspaper'),
                'description': cat_data.get('description', '')
            }
        )
        categories_map[cat.nom] = cat
        print(f"  - {cat.nom} {'(créé)' if created else '(existant)'}")
    return categories_map

def create_etablissements(data):
    """Crée les établissements"""
    print("Création des établissements...")
    etablissements_map = {}
    for etab_data in data.get('etablissements', []):
        etab, created = Etablissement.objects.get_or_create(
            nom=etab_data['nom'],
            defaults={
                'province': etab_data.get('province', '')
            }
        )
        etablissements_map[etab.nom] = etab
        print(f"  - {etab.nom} {'(créé)' if created else '(existant)'}")
    return etablissements_map

def create_organisations(data):
    """Crée les organisations"""
    print("Création des organisations...")
    organisations_map = {}
    for org_data in data.get('organisations', []):
        org, created = Organisation.objects.get_or_create(
            nom=org_data['nom'],
            defaults={
                'type': org_data.get('type', 'autre'),
                'description': org_data.get('description', '')
            }
        )
        organisations_map[org.nom] = org
        print(f"  - {org.nom} {'(créé)' if created else '(existant)'}")
    return organisations_map

def create_tags(data):
    """Crée les tags"""
    print("Création des tags...")
    tags_map = {}
    for tag_data in data.get('tags', []):
        tag, created = Tag.objects.get_or_create(
            nom=tag_data['nom']
        )
        tags_map[tag.nom] = tag
        print(f"  - {tag.nom} {'(créé)' if created else '(existant)'}")
    return tags_map

def parse_date(date_str):
    """Parse une date ISO en datetime aware"""
    if not date_str:
        return None
    if date_str.endswith('Z'):
        date_str = date_str[:-1] + '+00:00'
    return datetime.fromisoformat(date_str)

def create_news(news_data, user, categories_map, etablissements_map, organisations_map, tags_map):
    """Crée une news avec toutes ses relations"""
    print(f"Création de la news: {news_data['titre']}")
    
    # Récupérer les objets liés
    categorie = categories_map.get(news_data.get('categorie_nom'))
    etablissement = etablissements_map.get(news_data.get('etablissement_nom')) if news_data.get('etablissement_nom') else None
    organisation = organisations_map.get(news_data.get('organisation_nom')) if news_data.get('organisation_nom') else None
    
    # Créer la news
    news = News.objects.create(
        slug=news_data['slug'],
        type=news_data.get('type', NewsType.INFORMATION),
        titre=news_data['titre'],
        description=news_data['description'],
        contenu=news_data.get('contenu', ''),
        auteur=user,
        categorie=categorie,
        etablissement=etablissement,
        organisation=organisation,
        province=news_data.get('province') or 'Estuaire',  # Valeur par défaut si null
        lieu=news_data.get('lieu') or 'En ligne',  # Valeur par défaut si null
        date_debut=parse_date(news_data.get('date_debut')),
        date_fin=parse_date(news_data.get('date_fin')),
        statut=news_data.get('statut', NewsStatutChoices.PUBLIE),
        visibilite=news_data.get('visibilite', Visibilite.PUBLIC),
        partages=news_data.get('partages', 0)
    )
    
    # Ajouter les tags
    tag_names = news_data.get('tags', [])
    for tag_name in tag_names:
        if tag_name in tags_map:
            news.tags.add(tags_map[tag_name])
    
    print(f"  - News créée avec ID {news.id}")
    
    # Créer les commentaires
    for comm_data in news_data.get('commentaires', []):
        commentaire = Commentaire.objects.create(
            news=news,
            auteur=user,
            type_contenu=TypeContenuCommentaire.TEXTE,
            contenu=comm_data['contenu'],
            est_epingle=comm_data.get('est_epingle', False)
        )
        print(f"    - Commentaire créé: {comm_data['contenu'][:30]}...")
    
    # Créer les réactions (une seule réaction par utilisateur par news)
    for reaction_data in news_data.get('reactions', []):
        reaction_type = reaction_data['type_reaction']
        count = reaction_data.get('count', 1)
        for i in range(count):
            # Utiliser des utilisateurs différents pour éviter la contrainte unique
            user_index = i % User.objects.count()
            reaction_user = User.objects.all()[user_index] if User.objects.count() > 0 else user
            # Vérifier si une réaction existe déjà pour cet utilisateur sur cette news
            if not ReactionNews.objects.filter(news=news, utilisateur=reaction_user).exists():
                ReactionNews.objects.create(
                    news=news,
                    utilisateur=reaction_user,
                    type_reaction=reaction_type
                )
        print(f"    - {count} réactions de type {reaction_type}")
    
    # Créer les vues
    vues_count = news_data.get('vues', 0)
    for i in range(vues_count):
        view_user = User.objects.all()[i % User.objects.count()] if User.objects.count() > 0 else user
        NewsVue.objects.create(
            news=news,
            utilisateur=view_user,
            adresse_ip='127.0.0.1'
        )
    print(f"    - {vues_count} vues créées")
    
    # Créer le sondage si présent
    if 'sondage' in news_data:
        sondage_data = news_data['sondage']
        sondage = Sondage.objects.create(
            news=news,
            titre=sondage_data['titre'],
            description=sondage_data.get('description', ''),
            question=sondage_data['question'],
            type_vote=sondage_data.get('type_vote', TypeVoteSondage.UNIQUE),
            anonymat=sondage_data.get('anonymat', True),
            visibilite_resultat=sondage_data.get('visibilite_resultat', VisibiliteResultatSondage.INSTANTANE),
            date_debut=parse_date(sondage_data['date_debut']),
            date_fin=parse_date(sondage_data['date_fin']),
            statut=SondageStatutChoices.ACTIF
        )
        print(f"    - Sondage créé: {sondage_data['titre']}")
        
        # Créer les choix du sondage
        for choix_data in sondage_data.get('choix', []):
            ChoixSondage.objects.create(
                sondage=sondage,
                libelle=choix_data['libelle'],
                ordre=choix_data.get('ordre', 0)
            )
            print(f"      - Choix ajouté: {choix_data['libelle']}")
    
    # Créer les documents joints si présents
    if 'documents' in news_data:
        for doc_data in news_data['documents']:
            DocumentJoint.objects.create(
                news=news,
                nom=doc_data['nom'],
                fichier=None,  # Pas de fichier réel pour les données de test
                taille=0,
                type='application/pdf'
            )
            print(f"    - Document joint créé: {doc_data['nom']}")
    
    # Créer la galerie d'images si présente
    if 'galerie' in news_data:
        for img_data in news_data['galerie']:
            NewsImageGalerie.objects.create(
                news=news,
                image=None,  # Pas d'image réelle pour les données de test
                legende=img_data.get('legende', ''),
                ordre=img_data.get('ordre', 0)
            )
            print(f"    - Image de galerie créée: {img_data.get('legende', 'Sans légende')}")
    
    return news

def cleanup_existing_data():
    """Nettoie les données existantes pour éviter les conflits"""
    print("Nettoyage des données existantes...")
    
    # Supprimer dans l'ordre inverse des dépendances
    NewsVue.objects.all().delete()
    ReactionNews.objects.all().delete()
    VoteSondage.objects.all().delete()
    ChoixSondage.objects.all().delete()
    Sondage.objects.all().delete()
    DocumentJoint.objects.all().delete()
    NewsImageGalerie.objects.all().delete()
    NewsMedia.objects.all().delete()
    Commentaire.objects.all().delete()
    News.objects.all().delete()
    Tag.objects.all().delete()
    Organisation.objects.all().delete()
    Etablissement.objects.all().delete()
    Categorie.objects.all().delete()
    
    print("Données existantes nettoyées.")

def main():
    """Fonction principale"""
    print("=" * 60)
    print("Chargement des données de test CIVITAS NEWS")
    print("=" * 60)
    
    # Charger le fichier JSON
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fixtures', 'sample_data.json')
    print(f"\nChargement du fichier: {json_path}")
    data = load_json_data(json_path)
    
    # Récupérer le tenant
    print("\nRécupération du tenant...")
    tenant = get_tenant()
    print(f"Tenant trouvé: {tenant.schema_name}")
    
    # Exécuter dans le contexte du tenant
    with tenant_context(tenant):
        # Nettoyer les données existantes
        cleanup_existing_data()
        
        # Récupérer le premier utilisateur
        print("\nRécupération de l'utilisateur...")
        user = get_first_user()
        print(f"Utilisateur trouvé: {user.username} (ID: {user.id})")
        
        # Créer les entités de référence
        categories_map = create_categories(data)
        etablissements_map = create_etablissements(data)
        organisations_map = create_organisations(data)
        tags_map = create_tags(data)
        
        # Créer les news
        print("\nCréation des news...")
        news_count = 0
        for news_data in data.get('news', []):
            try:
                create_news(news_data, user, categories_map, etablissements_map, organisations_map, tags_map)
                news_count += 1
            except Exception as e:
                print(f"ERREUR lors de la création de la news '{news_data.get('titre', 'N/A')}': {e}")
                import traceback
                traceback.print_exc()
        
        print("\n" + "=" * 60)
        print(f"Terminé! {news_count} news créées avec succès.")
        print("=" * 60)

if __name__ == '__main__':
    main()
