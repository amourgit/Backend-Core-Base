"""
scripts/seed_news_demo.py
==========================

Peuple un tenant avec des données de démonstration complètes autour de
News (référentiels, commentaires, sondages, liens de partage, vues et
réactions) à partir de scripts/seed_news_demo.json.

NE PAS exécuter directement avec `python scripts/seed_news_demo.py`
(Django ne serait pas initialisé) -- ce script est prévu pour être
redirigé dans `manage.py shell`, qui a déjà appelé django.setup() avant
de l'exécuter. Voir scripts/seed_news_demo.sh pour l'invocation complète
(activation du venv, choix du tenant, redirection).

Variables d'environnement lues :
  SEED_TENANT_SCHEMA (obligatoire) -- schema_name du tenant cible.
  SEED_JSON_PATH     (optionnel)   -- chemin du fichier JSON, par défaut
                                      scripts/seed_news_demo.json à côté
                                      de ce script.

Idempotent : les référentiels (catégories/organisations/établissements/
tags) sont get_or_create sur leur champ naturellement unique. Les News
sont get_or_create sur leur slug -- si une News existe déjà, elle et
tout son contenu associé (commentaires/sondage/lien) sont laissés
INCHANGÉS et simplement signalés, pour ne jamais dupliquer en rejouant
le script.
"""
import json
import os
import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import transaction
from django_tenants.utils import schema_context

from referentiels.models import Categorie, Organisation, Etablissement
from news.models import News, Tag, NewsVue, ReactionNews, TypeReaction
from commentaires.models import Commentaire
from sondages.models import Sondage, ChoixSondage
from liens.models import LienPublication

User = get_user_model()


def log(message):
    print(f"  {message}")


def section(title):
    print(f"\n=== {title} ===")


def resolve_tenant_schema():
    schema = os.environ.get("SEED_TENANT_SCHEMA", "").strip()
    if schema:
        return schema

    from tenants.models import Tenant

    candidats = list(Tenant.objects.filter(is_active=True).exclude(schema_name="public"))
    if len(candidats) == 1:
        schema = candidats[0].schema_name
        log(f"Aucun tenant précisé -- un seul tenant actif trouvé, utilisation automatique de « {schema} ».")
        return schema

    noms = ", ".join(t.schema_name for t in candidats) or "(aucun)"
    print(
        "\n❌ SEED_TENANT_SCHEMA n'est pas défini, et plusieurs tenants (ou aucun) "
        f"sont disponibles pour choisir automatiquement.\n"
        f"   Tenants actifs disponibles : {noms}\n"
        "   Relancez via scripts/seed_news_demo.sh <sous-domaine>, ou :\n"
        "   SEED_TENANT_SCHEMA=<sous-domaine> python manage.py shell < scripts/seed_news_demo.py\n"
    )
    sys.exit(1)


def resolve_json_path():
    default_path = Path(__file__).resolve().parent / "seed_news_demo.json"
    return Path(os.environ.get("SEED_JSON_PATH", str(default_path)))


def get_or_bootstrap_author():
    """Premier utilisateur de la table (le plus ancien, par id). Si le
    tenant n'a encore AUCUN utilisateur, en crée un de secours plutôt que
    d'échouer -- `News.auteur` est un champ obligatoire (PROTECT), sans
    utilisateur aucune News ne peut exister."""
    auteur = User.objects.order_by("id").first()
    if auteur:
        log(f"Auteur : utilisateur existant '{auteur.username}' (id={auteur.id})")
        return auteur

    import secrets

    mot_de_passe = secrets.token_urlsafe(18)
    auteur = User.objects.create_user(
        username="redaction",
        email="redaction@civitas-news.local",
        first_name="Rédaction",
        last_name="CIVITAS NEWS",
        password=mot_de_passe,
        role="administrateur",
        is_verified=True,
    )
    print(
        "\n⚠️  Aucun utilisateur n'existait dans ce tenant -- compte de "
        "secours créé pour servir d'auteur :\n"
        f"    username: {auteur.username}\n"
        f"    password: {mot_de_passe}\n"
        "    (à noter maintenant, ce mot de passe ne sera plus jamais affiché)\n"
    )
    return auteur


def seed_referentiels(data):
    section("Référentiels")
    categories, organisations, etablissements = {}, {}, {}

    for c in data["categories"]:
        obj, created = Categorie.objects.get_or_create(
            nom=c["nom"],
            defaults={"couleur": c["couleur"], "icone": c["icone"], "description": c.get("description", "")},
        )
        categories[c["ref"]] = obj
        log(f"{'✅ créée' if created else 'ℹ️  déjà présente'} — catégorie « {obj.nom} »")

    for o in data["organisations"]:
        obj, created = Organisation.objects.get_or_create(
            nom=o["nom"],
            defaults={"type": o["type"], "description": o.get("description", "")},
        )
        organisations[o["ref"]] = obj
        log(f"{'✅ créée' if created else 'ℹ️  déjà présente'} — organisation « {obj.nom} »")

    for e in data["etablissements"]:
        obj, created = Etablissement.objects.get_or_create(
            nom=e["nom"],
            defaults={"province": e["province"]},
        )
        etablissements[e["ref"]] = obj
        log(f"{'✅ créé' if created else 'ℹ️  déjà présent'} — établissement « {obj.nom} »")

    return categories, organisations, etablissements


def seed_commentaires(news, auteur, commentaires_data):
    for c in commentaires_data:
        commentaire = Commentaire.objects.create(news=news, auteur=auteur, contenu=c["contenu"])
        for r in c.get("reponses", []):
            Commentaire.objects.create(news=news, auteur=auteur, contenu=r["contenu"], reponse_a=commentaire)
    if commentaires_data:
        total = len(commentaires_data) + sum(len(c.get("reponses", [])) for c in commentaires_data)
        log(f"    💬 {total} commentaire(s) créé(s)")


def seed_sondage(news, sondage_data):
    if not sondage_data:
        return
    sondage = Sondage.objects.create(
        news=news,
        titre=sondage_data["titre"],
        question=sondage_data["question"],
        description=sondage_data.get("description", ""),
        date_debut=sondage_data["date_debut"],
        date_fin=sondage_data["date_fin"],
        type_vote=sondage_data.get("type_vote", "unique"),
    )
    for ordre, libelle in enumerate(sondage_data["choix"]):
        ChoixSondage.objects.create(sondage=sondage, libelle=libelle, ordre=ordre)
    log(f"    🗳️  sondage « {sondage.titre} » créé ({len(sondage_data['choix'])} choix)")


def seed_lien(news, lien_data):
    if not lien_data:
        return
    from django.conf import settings

    lien = LienPublication.objects.create(
        news=news,
        url_publique=f"{settings.FRONTEND_BASE_URL}/news/{news.slug}",
        visibilite=lien_data.get("visibilite", "public"),
        scope_etablissement=lien_data.get("scope_etablissement", ""),
        scope_province=lien_data.get("scope_province", ""),
    )
    log(f"    🔗 lien de partage créé (code court : {lien.code_court})")


def seed_activite(news, auteur):
    """Quelques vues + une réaction, pour que les statistiques affichées
    ne soient pas toutes à zéro. Volontairement minimal : un seul
    utilisateur disponible dans un tenant fraîchement peuplé, pas la
    peine de fabriquer de faux comptes supplémentaires pour ça."""
    for _ in range(3):
        NewsVue.objects.create(news=news, utilisateur=None)  # visiteurs anonymes
    NewsVue.objects.create(news=news, utilisateur=auteur)
    ReactionNews.objects.get_or_create(news=news, utilisateur=auteur, defaults={"type_reaction": TypeReaction.JAIME})


def seed_news(data, categories, organisations, etablissements, auteur):
    section("News")
    creees, existantes = 0, 0

    for n in data["news"]:
        if News.objects.filter(slug=n["slug"]).exists():
            log(f"ℹ️  déjà présente — « {n['titre']} » (slug={n['slug']}), contenu associé inchangé")
            existantes += 1
            continue

        with transaction.atomic():
            news = News.objects.create(
                slug=n["slug"],
                type=n["type"],
                titre=n["titre"],
                description=n["description"],
                contenu=n.get("contenu", ""),
                auteur=auteur,
                categorie=categories[n["categorie_ref"]],
                organisation=organisations.get(n.get("organisation_ref")),
                etablissement=etablissements.get(n.get("etablissement_ref")),
                province=n.get("province", ""),
                lieu=n.get("lieu", ""),
                date_debut=n.get("date_debut"),
                date_fin=n.get("date_fin"),
                statut=n.get("statut", "publie"),
                visibilite=n.get("visibilite", "public"),
            )
            if n.get("tags"):
                tags = [Tag.objects.get_or_create(nom=t)[0] for t in n["tags"]]
                news.tags.set(tags)

            seed_commentaires(news, auteur, n.get("commentaires", []))
            seed_sondage(news, n.get("sondage"))
            seed_lien(news, n.get("lien_partage"))
            if news.statut == "publie":
                seed_activite(news, auteur)

        log(f"✅ créée — « {news.titre} » (slug={news.slug}, statut={news.statut})")
        creees += 1

    return creees, existantes


def run():
    schema = resolve_tenant_schema()
    json_path = resolve_json_path()
    if not json_path.exists():
        print(f"\n❌ Fichier introuvable : {json_path}\n")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Tenant cible : {schema}")
    print(f"Fichier de données : {json_path}")

    with schema_context(schema):
        auteur = get_or_bootstrap_author()
        categories, organisations, etablissements = seed_referentiels(data)
        creees, existantes = seed_news(data, categories, organisations, etablissements, auteur)

    section("Résumé")
    log(f"News créées : {creees}")
    log(f"News déjà présentes (ignorées) : {existantes}")
    print("\n✅ Terminé.\n")


run()
