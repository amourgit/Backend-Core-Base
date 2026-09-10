"""
scripts/seed_news_demo.py
==========================

Peuple un tenant avec des données de démonstration complètes autour de
News : référentiels, utilisateurs, badges, commentaires (avec votes et
réactions), sondages (avec votes réels), liens de partage (avec accès
clics/scans), signalements et notifications -- à partir de
scripts/seed_news_demo.json.

NE PAS exécuter directement avec `python scripts/seed_news_demo.py`
(Django ne serait pas initialisé) -- ce script est prévu pour être
redirigé dans `manage.py shell`, qui a déjà appelé django.setup() avant
de l'exécuter. Voir scripts/seed_news_demo.sh pour l'invocation complète
(activation du venv, choix du tenant, redirection).

Variables d'environnement lues :
  SEED_TENANT_SCHEMA (obligatoire, auto-détectée si un seul tenant actif)
  SEED_JSON_PATH     (optionnel) -- chemin du fichier JSON, par défaut
                                     scripts/seed_news_demo.json.

Idempotent : les référentiels (catégories/organisations/établissements/
tags/badges/utilisateurs) sont get_or_create sur leur champ naturellement
unique. Les News sont get_or_create sur leur slug -- si une News existe
déjà, elle et TOUT son contenu associé (commentaires/votes/réactions/
sondage/lien/accès/signalements) sont laissés INCHANGÉS et simplement
signalés, pour ne jamais dupliquer en rejouant le script.

Mot de passe commun à tous les comptes de démonstration créés ici (PAS
le compte de secours "auteur", qui a son propre mot de passe aléatoire
affiché une seule fois) : voir DEMO_PASSWORD ci-dessous.
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
from commentaires.models import Commentaire, VoteCommentaire, ReactionCommentaire
from sondages.models import Sondage, ChoixSondage, VoteSondage
from liens.models import LienPublication, LienAcces
from moderation.models import Signalement
from notifications.models import Notification
from users.models import Badge

User = get_user_model()

# Mot de passe commun à tous les comptes de démonstration (amina_k,
# jean_d, marie_l, diallo_mod, okemba_admin, aec_officiel) -- des
# comptes explicitement destinés à être utilisés pour tester l'app
# sous différents rôles, pas des comptes de production : pas la peine
# d'un mot de passe aléatoire par compte comme pour l'auteur de secours.
DEMO_PASSWORD = "Demo1234!"


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
    utilisateur aucune News ne peut exister. Les comptes de démo créés
    par seed_utilisateurs() ci-dessous n'existent pas encore à ce stade
    (créés juste après), donc ce premier utilisateur est indépendant
    d'eux -- exactement le comportement demandé : "le premier
    utilisateur de la table users", peu importe d'où il vient."""
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


def seed_badges(data):
    section("Badges")
    badges = {}
    for b in data.get("badges", []):
        obj, created = Badge.objects.get_or_create(
            nom=b["nom"], defaults={"icone": b["icone"], "description": b.get("description", "")}
        )
        badges[b["ref"]] = obj
        log(f"{'✅ créé' if created else 'ℹ️  déjà présent'} — badge « {obj.nom} »")
    return badges


def seed_utilisateurs(data, badges):
    """Comptes de démonstration (distincts de l'auteur de secours
    éventuel). Chacun peut se connecter avec DEMO_PASSWORD pour tester
    l'app sous son rôle. get_or_create sur `username` : si le compte
    existe déjà (créé lors d'un rejeu précédent, ou par Samuel lui-même
    via /auth/register), il est réutilisé tel quel -- mot de passe et
    rôle existants jamais écrasés."""
    section("Utilisateurs de démonstration")
    utilisateurs = {}
    for u in data.get("utilisateurs", []):
        obj, created = User.objects.get_or_create(
            username=u["username"],
            defaults={
                "email": u["email"],
                "first_name": u["first_name"],
                "last_name": u["last_name"],
                "role": u["role"],
                "is_verified": True,
            },
        )
        if created:
            obj.set_password(DEMO_PASSWORD)
            obj.save(update_fields=["password"])
        utilisateurs[u["ref"]] = obj

        badge_refs = u.get("badges", [])
        if badge_refs:
            obj.badges.add(*[badges[ref] for ref in badge_refs])

        log(f"{'✅ créé' if created else 'ℹ️  déjà présent'} — {obj.get_role_display()} « {obj.username} »")

    return utilisateurs


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


def seed_commentaires(news, auteur_defaut, utilisateurs, commentaires_data):
    """Crée les commentaires (et leurs réponses imbriquées), avec votes
    et réactions de différents utilisateurs -- et notifie l'auteur de
    la News à chaque commentaire de premier niveau si l'auteur du
    commentaire est différent de lui."""
    total_commentaires = 0
    total_votes = 0
    total_reactions = 0

    def resoudre_auteur(ref):
        return utilisateurs[ref] if ref else auteur_defaut

    def appliquer_votes_reactions(commentaire, entry):
        nonlocal total_votes, total_reactions
        for v in entry.get("votes", []):
            VoteCommentaire.objects.get_or_create(
                commentaire=commentaire, utilisateur=utilisateurs[v["utilisateur_ref"]],
                defaults={"direction": v["direction"]},
            )
            total_votes += 1
        for r in entry.get("reactions", []):
            ReactionCommentaire.objects.get_or_create(
                commentaire=commentaire, utilisateur=utilisateurs[r["utilisateur_ref"]],
                type_reaction=r["type_reaction"],
            )
            total_reactions += 1

    for c in commentaires_data:
        auteur_commentaire = resoudre_auteur(c.get("auteur_ref"))
        commentaire = Commentaire.objects.create(news=news, auteur=auteur_commentaire, contenu=c["contenu"])
        total_commentaires += 1
        appliquer_votes_reactions(commentaire, c)

        if auteur_commentaire != news.auteur:
            notifier(
                news.auteur, format_="actualite", titre="Nouveau commentaire",
                description=f"{auteur_commentaire.get_full_name() or auteur_commentaire.username} a commenté « {news.titre} ».",
                categorie_nom="Commentaires", categorie_couleur="#5B4DFF", categorie_icone="MessageCircle",
                lien=f"/news?news={news.slug}",
            )

        for r in c.get("reponses", []):
            auteur_reponse = resoudre_auteur(r.get("auteur_ref"))
            reponse = Commentaire.objects.create(
                news=news, auteur=auteur_reponse, contenu=r["contenu"], reponse_a=commentaire,
            )
            total_commentaires += 1
            appliquer_votes_reactions(reponse, r)
            if auteur_reponse != auteur_commentaire:
                notifier(
                    auteur_commentaire, format_="actualite", titre="Réponse à votre commentaire",
                    description=f"{auteur_reponse.get_full_name() or auteur_reponse.username} vous a répondu sur « {news.titre} ».",
                    categorie_nom="Commentaires", categorie_couleur="#5B4DFF", categorie_icone="MessageCircle",
                    lien=f"/news?news={news.slug}",
                )

    if total_commentaires:
        log(f"    💬 {total_commentaires} commentaire(s), {total_votes} vote(s), {total_reactions} réaction(s)")


def seed_sondage(news, utilisateurs, sondage_data):
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
    choix_par_index = []
    for ordre, libelle in enumerate(sondage_data["choix"]):
        choix_par_index.append(ChoixSondage.objects.create(sondage=sondage, libelle=libelle, ordre=ordre))

    total_votes = 0
    for v in sondage_data.get("votes", []):
        choix = choix_par_index[v["choix_index"]]
        for ref in v["utilisateur_refs"]:
            VoteSondage.objects.get_or_create(sondage=sondage, choix=choix, utilisateur=utilisateurs[ref])
            total_votes += 1

    log(f"    🗳️  sondage « {sondage.titre} » créé ({len(choix_par_index)} choix, {total_votes} vote(s))")


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
    for _ in range(lien_data.get("acces_clics", 0)):
        LienAcces.objects.create(lien=lien, type_acces="clic")
    for _ in range(lien_data.get("acces_scans", 0)):
        LienAcces.objects.create(lien=lien, type_acces="scan")

    log(f"    🔗 lien de partage créé (code court : {lien.code_court}, "
        f"{lien_data.get('acces_clics', 0)} clic(s), {lien_data.get('acces_scans', 0)} scan(s))")


def seed_signalements(news, utilisateurs, signalements_data):
    if not signalements_data:
        return
    for s in signalements_data:
        Signalement.objects.create(
            type_contenu="news",
            contenu_id=str(news.id),
            titre_ou_apercu=news.titre[:255],
            motif=s["motif"],
            description=s.get("description", ""),
            auteur_signalement=utilisateurs[s["auteur_ref"]],
            statut=s.get("statut", "en_attente"),
        )
    log(f"    🚩 {len(signalements_data)} signalement(s) créé(s)")


def notifier(destinataire, *, format_, titre, description, categorie_nom, categorie_couleur, categorie_icone, lien):
    Notification.objects.create(
        destinataire=destinataire,
        format=format_,
        titre=titre,
        description=description,
        categorie_nom=categorie_nom,
        categorie_couleur=categorie_couleur,
        categorie_icone=categorie_icone,
        lien=lien,
    )


def seed_activite(news, auteur):
    """Quelques vues + une réaction de l'auteur, en plus des votes/
    réactions déjà générés par les commentaires/sondages ci-dessus."""
    for _ in range(3):
        NewsVue.objects.create(news=news, utilisateur=None)  # visiteurs anonymes
    NewsVue.objects.create(news=news, utilisateur=auteur)
    ReactionNews.objects.get_or_create(news=news, utilisateur=auteur, defaults={"type_reaction": TypeReaction.JAIME})


def seed_news(data, categories, organisations, etablissements, utilisateurs, auteur_defaut):
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
                auteur=auteur_defaut,
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

            seed_commentaires(news, auteur_defaut, utilisateurs, n.get("commentaires", []))
            seed_sondage(news, utilisateurs, n.get("sondage"))
            seed_lien(news, n.get("lien_partage"))
            seed_signalements(news, utilisateurs, n.get("signalements"))
            if news.statut == "publie":
                seed_activite(news, auteur_defaut)

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
        auteur_defaut = get_or_bootstrap_author()
        badges = seed_badges(data)
        utilisateurs = seed_utilisateurs(data, badges)
        categories, organisations, etablissements = seed_referentiels(data)
        creees, existantes = seed_news(data, categories, organisations, etablissements, utilisateurs, auteur_defaut)

    section("Résumé")
    log(f"Comptes de démonstration : {len(utilisateurs)} (mot de passe : {DEMO_PASSWORD})")
    log(f"News créées : {creees}")
    log(f"News déjà présentes (ignorées) : {existantes}")
    print("\n✅ Terminé.\n")


run()
