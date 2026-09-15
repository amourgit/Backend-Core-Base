from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django_tenants.models import TenantMixin
from django.utils.text import slugify
from django.db import connection
from django.db import transaction
from django.core.exceptions import ValidationError
from django.conf import settings
from django_tenants.utils import schema_context
import re
import os
import secrets
import string
from django.apps import apps
from django.db.migrations.loader import MigrationLoader

from common.models import SocleTracabilite, PeriodeValiditeMixin
from common.storage import get_raw_media_storage

User = get_user_model()

class Tenant(TenantMixin):
    """
    Modèle représentant un tenant dans le système multi-tenant.
    Chaque tenant a son propre schéma de base de données.
    """
    auto_create_schema = True
    auto_drop_schema = True
    
    name = models.CharField(_('Nom'), max_length=100)
    sous_domaine = models.CharField(_('Sous-domaine'), max_length=100, unique=True)
    schema_name = models.CharField(_('Nom du schéma'), max_length=63, unique=True)
    is_active = models.BooleanField(_('Actif'), default=False)
    is_public = models.BooleanField(
        _('Public'),
        default=False,
        help_text=_(
            "Si activé, ce tenant est inclus automatiquement dans la liste "
            "de tenants que le frontend ajoute à CHAQUE requête GET (en plus "
            "du tenant courant de l'utilisateur) -- voir "
            "tenants.middleware.TenantMiddleware._fan_out_get. Réservé aux "
            "organisations dont le contenu doit être visible par tous les "
            "usagers de la plateforme, quel que soit leur propre tenant "
            "d'appartenance (ex: Ministères, Mutuelles)."
        ),
    )
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Mis à jour le'), auto_now=True)
    description = models.TextField(_('Description'), blank=True)
    logo = models.ImageField(_('Logo'), upload_to='tenant_logos/', null=True, blank=True)
    settings = models.JSONField(_('Paramètres'), default=dict, blank=True)

    class Meta:
        verbose_name = _('Tenant')
        verbose_name_plural = _('Tenants')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.sous_domaine})"

    def save(self, *args, **kwargs):
        """Surcharge de save() pour automatiser certaines opérations."""
        if not self.schema_name:
            self.schema_name = slugify(self.sous_domaine).replace('-', '_')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Surcharge de delete() pour nettoyer le schéma."""
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{self.schema_name}" CASCADE')
        except Exception as e:
            print(f"⚠️ Erreur suppression schéma {self.schema_name}: {str(e)}")
        super().delete(*args, **kwargs)

    def clean(self):
        """Validation des données avant sauvegarde."""
        super().clean()
        
        if self.sous_domaine:
            if not re.match(r'^[a-z0-9-]+$', self.sous_domaine):
                raise ValidationError(
                    _('Le sous-domaine ne peut contenir que des lettres minuscules, des chiffres et des tirets')
                )
                
            if len(self.sous_domaine) < 3:
                raise ValidationError(
                    _('Le sous-domaine doit contenir au moins 3 caractères')
                )

    @property
    def is_accessible(self):
        """Vérifie si le tenant est accessible."""
        return self.is_active and self.schema_name

    @classmethod
    def create_with_domain(cls, name: str, sous_domaine: str, identifiant: str, password: str = None, description: str = '', **kwargs):
        """
        Factory method pour créer un tenant avec son domaine et son
        premier administrateur -- créé DANS le schéma du tenant (chaque
        tenant est autonome pour ses utilisateurs, voir config/settings.py :
        users/auth/admin double-listés SHARED_APPS + TENANT_APPS), avec
        à la fois is_staff=is_superuser=True (accès Django admin complet
        sur ce schéma) ET role=RoleUtilisateur.ADMINISTRATEUR (rôle
        APPLICATIF vérifié par common.permissions.a_role -- les deux sont
        indépendants, voir bootstrap_tenant.py::_create_admin qui suit le
        même principe).

        `identifiant` : email OU numéro de téléphone (même détection
        automatique qu'à l'inscription self-service, voir
        UsersService/IdentifiantRegisterSerializer) -- remplace les
        anciens admin_email/admin_username séparés, pour rester cohérent
        avec le SEUL mode de création de compte qui existe ailleurs dans
        l'app.
        """
        from domain.models import Domain
        from users.api.v1.services import UsersService, normaliser_identifiant, is_email, is_telephone_valide
        from users.models import RoleUtilisateur
        import secrets
        import string
        
        try:
            # 1. Validation des paramètres
            if not name or not sous_domaine or not identifiant:
                raise ValidationError("Nom, sous-domaine et identifiant administrateur requis")
            
            if not settings.MAIN_DOMAIN:
                raise ValidationError("MAIN_DOMAIN non configuré dans les paramètres")

            identifiant = normaliser_identifiant(identifiant)
            if not identifiant or not (is_email(identifiant) or is_telephone_valide(identifiant)):
                raise ValidationError("L'identifiant administrateur doit être un email ou un numéro de téléphone valide")
            
            # 2. Préparation des données
            schema_name = slugify(sous_domaine).replace('-', '_')
            domain_name = f"{sous_domaine}.{settings.MAIN_DOMAIN}"
            
            # 3. Vérification des doublons
            if cls.objects.filter(sous_domaine=sous_domaine).exists():
                raise ValidationError(f"Le sous-domaine '{sous_domaine}' existe déjà")
                
            if cls.objects.filter(schema_name=schema_name).exists():
                raise ValidationError(f"Le schéma '{schema_name}' existe déjà")
                
            if Domain.objects.filter(domain=domain_name).exists():
                raise ValidationError(f"Le domaine '{domain_name}' existe déjà")
            
            # 4. Création atomique du tenant et du domaine
            with transaction.atomic():
                # Création du tenant
                tenant = cls(
                    name=name,
                    sous_domaine=sous_domaine,
                    schema_name=schema_name,
                    description=description,
                    **kwargs
                )
                tenant.full_clean()
                tenant.save()
                
                # Création du domaine
                domain = Domain.objects.create(
                    tenant=tenant,
                    domain=domain_name,
                    is_primary=True
                )
                
                # 5. Le schéma et ses migrations sont déjà en place à ce
                # stade : `tenant.save()` (étape 4 ci-dessus) les a créés
                # automatiquement via TenantMixin (auto_create_schema=True,
                # voir django_tenants/models.py::save -> create_schema()
                # -> migrate_schemas). Répéter ici une création de schéma
                # + un migrate explicite était totalement redondant --
                # ça faisait tourner TOUTES les migrations DEUX FOIS sur
                # la même requête HTTP, ce qui pouvait à lui seul dépasser
                # le WORKER TIMEOUT de gunicorn (voir gunicorn.conf.py) et
                # faire échouer la création avec un 500. Supprimé.
                #
                # Le tenant est créé is_active=False par défaut (voir le
                # champ du modèle) : c'est désormais l'administrateur
                # global qui l'active depuis l'admin Django natif (schéma
                # public), jamais automatiquement à la création.

                # 6. Création de l'administrateur DANS le schéma du tenant
                # (superuser Django + role applicatif ADMINISTRATEUR --
                # voir docstring de la méthode).
                admin_credentials = {}
                with schema_context(schema_name):
                    # Génération du mot de passe si non fourni
                    if not password:
                        password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
                    
                    try:
                        print(f"👤 Création de l'administrateur pour {schema_name}")
                        UsersService.creer_utilisateur_depuis_identifiant(
                            identifiant, password,
                            is_staff=True, is_superuser=True, role=RoleUtilisateur.ADMINISTRATEUR,
                        )
                        admin_credentials = {
                            'identifiant': identifiant,
                            'password': password,
                        }
                        print(f"✅ Administrateur créé avec succès pour {schema_name}")
                    except Exception as e:
                        print(f"❌ Erreur lors de la création de l'administrateur: {str(e)}")
                        raise ValidationError(f"Erreur lors de la création de l'administrateur: {str(e)}")
                
                return tenant, domain, admin_credentials
                
        except Exception as e:
            # En cas d'erreur, on nettoie le schéma si créé
            if 'tenant' in locals() and hasattr(tenant, 'schema_name'):
                try:
                    print(f"🧹 Nettoyage du schéma {tenant.schema_name} suite à une erreur")
                    with connection.cursor() as cursor:
                        cursor.execute(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE;')
                except Exception as cleanup_error:
                    print(f"⚠️ Erreur lors du nettoyage du schéma: {str(cleanup_error)}")
            raise ValidationError(str(e))


class TenantAwareModel(models.Model):
    """
    Classe de base pour les modèles qui doivent être conscients du tenant.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Informations d'identité, documents requis et documents génériques d'un
# tenant — extension purement ADDITIVE du Socle de Traçabilité (voir
# common/models.py) : aucun champ existant de `Tenant` n'est touché.
#
# Contexte : les champs natifs de `Tenant` ci-dessus (name, description,
# logo, settings) restent volontairement minimalistes — une carte
# d'identité "vitrine", affichée publiquement (TenantPublicSerializer).
# Ce qui suit répond à un besoin différent : recueillir une fiche
# d'identité complète de l'organisation (utile à la plateforme pour ses
# études, et au tenant lui-même) ainsi que les documents administratifs
# qu'elle doit ou peut fournir. Trois tables :
#
#   - TenantInformationsPrimaires : fiche d'identité (une par tenant).
#   - TenantDocumentRequis        : soumissions pour un catalogue de types
#                                   de documents FIXÉ dans le code (voir
#                                   `TypeDocumentRequis` /
#                                   `ContraintesDocumentRequis` ci-dessous)
#                                   — ajouter un type ne nécessite AUCUNE
#                                   migration de base de données.
#   - TenantDocumentGenerique     : dépôt libre pour tout document que le
#                                   catalogue fixe n'a pas anticipé.
#
# Point d'architecture important : ces trois modèles vivent dans l'app
# 'tenants' (SHARED_APPS, schéma PUBLIC uniquement — voir
# config/settings.py). Or `cree_par`/`modifie_par`/`supprime_par`
# (hérités de SocleTracabilite) sont des FK vers AUTH_USER_MODEL,
# contraintes à la migration à la table `users_user` du schéma PUBLIC —
# alors que l'immense majorité des écritures sur ces 3 tables proviennent
# d'un ADMINISTRATEUR DE TENANT, dont le compte vit dans la table
# `users_user` PROPRE à son schéma (voir le double listage `users` dans
# SHARED_APPS + TENANT_APPS, config/settings.py) : un pk qui n'a AUCUN
# rapport avec ceux du schéma public. Lui assigner `request.user` tel
# quel écrirait donc soit un pk inexistant côté public (IntegrityError),
# soit — pire — un pk qui existe par coïncidence mais désigne une tout
# autre personne. Voir `tenants/api/v1/mixins.py`
# (SharedTenantScopedModelViewSet) et `common/admin.py`
# (TenantScopedAdminMixin) pour la traçabilité "sûre du point de vue
# schéma" appliquée à l'API et à l'admin Django : `cree_par`/`modifie_par`
# (la vraie FK) ne sont renseignés que depuis le schéma public (un
# administrateur de PLATEFORME) ; sinon on utilise les champs texte
# libres `cree_par_systeme`/`modifie_par_systeme`, prévus par le Socle
# pour exactement ce cas.
# ---------------------------------------------------------------------------

class FormeJuridique(models.TextChoices):
    """Nature juridique de l'organisation porteuse du tenant. Liste fixe
    et volontairement large : un tenant peut être une école, un
    ministère, un média, une mutuelle, une association... (voir
    `Tenant.is_public`, déjà pensé pour cette diversité)."""
    ASSOCIATION = 'association', _('Association')
    ONG = 'ong', _('ONG')
    ETABLISSEMENT_PUBLIC = 'etablissement_public', _('Établissement public')
    ETABLISSEMENT_PRIVE = 'etablissement_prive', _('Établissement privé')
    MINISTERE_OU_ADMINISTRATION = 'ministere_administration', _('Ministère / Administration publique')
    ENTREPRISE_PRIVEE = 'entreprise_privee', _('Entreprise privée')
    ENTREPRISE_PUBLIQUE = 'entreprise_publique', _('Entreprise publique / parapublique')
    MUTUELLE = 'mutuelle', _('Mutuelle')
    MEDIA = 'media', _('Média')
    AUTRE = 'autre', _('Autre')


class SecteurActivite(models.TextChoices):
    """Secteur d'activité principal — liste fixe, même logique que
    `FormeJuridique` ci-dessus."""
    EDUCATION_FORMATION = 'education_formation', _('Éducation / Formation')
    SANTE = 'sante', _('Santé')
    ADMINISTRATION_PUBLIQUE = 'administration_publique', _('Administration publique')
    MEDIA_COMMUNICATION = 'media_communication', _('Média / Communication')
    ASSOCIATIF_HUMANITAIRE = 'associatif_humanitaire', _('Associatif / Humanitaire')
    ECONOMIE_FINANCE = 'economie_finance', _('Économie / Finance')
    PROTECTION_SOCIALE = 'protection_sociale', _('Protection sociale / Mutualité')
    AUTRE = 'autre', _('Autre')


class ProvinceGabon(models.TextChoices):
    """Les 9 provinces du Gabon — liste fixe, ne justifie pas une table de
    référence dédiée. Dupliquée ici à l'identique plutôt qu'importée
    depuis `news.models.Province` : 'tenants' est une app SHARED_APPS,
    'news' une app TENANT_APPS — mieux vaut ne pas faire dépendre une app
    publique du module interne d'une app par-tenant pour un enum figé de
    9 valeurs."""
    ESTUAIRE = 'estuaire', _('Estuaire')
    HAUT_OGOOUE = 'haut_ogooue', _('Haut-Ogooué')
    MOYEN_OGOOUE = 'moyen_ogooue', _('Moyen-Ogooué')
    NGOUNIE = 'ngounie', _('Ngounié')
    NYANGA = 'nyanga', _('Nyanga')
    OGOOUE_IVINDO = 'ogooue_ivindo', _('Ogooué-Ivindo')
    OGOOUE_LOLO = 'ogooue_lolo', _('Ogooué-Lolo')
    OGOOUE_MARITIME = 'ogooue_maritime', _('Ogooué-Maritime')
    WOLEU_NTEM = 'woleu_ntem', _('Woleu-Ntem')


class StatutVerificationIdentite(models.TextChoices):
    """Cycle de vie MÉTIER propre à `TenantInformationsPrimaires`, qui
    redéfinit `statut` — même principe que News/Sondage pour
    `SocleTracabilite.statut` (voir common/models.py)."""
    A_COMPLETER = 'a_completer', _('À compléter')
    EN_ATTENTE_VERIFICATION = 'en_attente_verification', _('En attente de vérification')
    VERIFIEE = 'verifiee', _('Vérifiée')
    A_CORRIGER = 'a_corriger', _('À corriger')


class TenantInformationsPrimaires(SocleTracabilite):
    """
    Fiche d'identité PRIMAIRE d'un tenant — une seule par tenant
    (OneToOne). Complète les champs "vitrine" de `Tenant` (name,
    description, logo) avec tout ce qui permet (1) à la plateforme
    d'exploiter des données d'ensemble sur ses tenants ("nos études"), et
    (2) au tenant lui-même de disposer d'une fiche institutionnelle
    complète. Créée à la volée au premier accès (get_or_create) plutôt
    que par un signal — voir `TenantDossierService.get_or_create_informations`
    (tenants/api/v1/services.py) : `tenants/signals.py` existe déjà dans
    ce dépôt mais n'est câblé nulle part (aucun `ready()` ne l'importe),
    autant ne pas ajouter une dépendance à un mécanisme déjà fragile.
    """
    statut = models.CharField(
        _('Statut de vérification'), max_length=30,
        choices=StatutVerificationIdentite.choices,
        default=StatutVerificationIdentite.A_COMPLETER, db_index=True,
    )

    tenant = models.OneToOneField(
        Tenant, verbose_name=_('Tenant'), on_delete=models.CASCADE,
        related_name='informations_primaires',
    )

    # --- Identification légale ---
    forme_juridique = models.CharField(_('Forme juridique'), max_length=40, choices=FormeJuridique.choices, blank=True)
    secteur_activite = models.CharField(_('Secteur d’activité'), max_length=40, choices=SecteurActivite.choices, blank=True)
    raison_sociale = models.CharField(
        _('Raison sociale / Dénomination officielle'), max_length=255, blank=True,
        help_text=_("Nom légal complet, distinct de `Tenant.name` qui reste le nom d'affichage court côté vitrine publique."),
    )
    sigle = models.CharField(_('Sigle / Acronyme'), max_length=30, blank=True)
    numero_rccm = models.CharField(_('Numéro RCCM'), max_length=50, blank=True, help_text=_('Registre du Commerce et du Crédit Mobilier.'))
    numero_nif = models.CharField(_('Numéro NIF'), max_length=50, blank=True, help_text=_("Numéro d'Identification Fiscale (DGI)."))
    numero_agrement = models.CharField(
        _("Numéro d'agrément / de récépissé"), max_length=50, blank=True,
        help_text=_("Pour une association/ONG : numéro d'agrément ministériel ou de récépissé de déclaration."),
    )
    date_creation_ou_agrement = models.DateField(_("Date de création / d'agrément"), null=True, blank=True)

    # --- Coordonnées ---
    adresse_siege = models.TextField(_('Adresse du siège'), blank=True)
    ville = models.CharField(_('Ville'), max_length=100, blank=True)
    province = models.CharField(_('Province'), max_length=20, choices=ProvinceGabon.choices, blank=True)
    pays = models.CharField(_('Pays'), max_length=100, default='Gabon')
    telephone_principal = models.CharField(_('Téléphone principal'), max_length=30, blank=True)
    telephone_secondaire = models.CharField(_('Téléphone secondaire'), max_length=30, blank=True)
    email_contact = models.EmailField(_('Email de contact'), blank=True)
    site_web = models.URLField(_('Site web'), max_length=300, blank=True)
    reseaux_sociaux = models.JSONField(
        _('Réseaux sociaux'), default=dict, blank=True,
        help_text=_(
            "Dictionnaire libre {plateforme: url} — même convention que "
            "`referentiels.Organisation.reseaux_sociaux`."
        ),
    )

    # --- Responsable légal ---
    responsable_nom_complet = models.CharField(_('Nom complet du responsable légal'), max_length=150, blank=True)
    responsable_fonction = models.CharField(_('Fonction du responsable légal'), max_length=100, blank=True)
    responsable_telephone = models.CharField(_('Téléphone du responsable légal'), max_length=30, blank=True)
    responsable_email = models.EmailField(_('Email du responsable légal'), blank=True)

    # --- Contact opérationnel (point focal au quotidien, si différent du responsable légal) ---
    contact_operationnel_nom = models.CharField(_('Nom du contact opérationnel'), max_length=150, blank=True)
    contact_operationnel_fonction = models.CharField(_('Fonction du contact opérationnel'), max_length=100, blank=True)
    contact_operationnel_telephone = models.CharField(_('Téléphone du contact opérationnel'), max_length=30, blank=True)
    contact_operationnel_email = models.EmailField(_('Email du contact opérationnel'), blank=True)

    # --- Données quantitatives / descriptives ("nos études") ---
    effectif_estime = models.PositiveIntegerField(
        _('Effectif estimé'), null=True, blank=True,
        help_text=_("Nombre approximatif de membres/employés/étudiants/adhérents, selon la nature du tenant."),
    )
    zone_couverture = models.TextField(
        _('Zone de couverture'), blank=True,
        help_text=_("Provinces/villes couvertes par l'activité du tenant (texte libre)."),
    )
    description_activites = models.TextField(
        _('Description détaillée des activités'), blank=True,
        help_text=_("Présentation complète, distincte de `Tenant.description` (résumé court côté vitrine publique)."),
    )

    # --- Suivi de la vérification par la plateforme ---
    commentaire_verification = models.TextField(
        _('Commentaire de vérification'), blank=True,
        help_text=_("Note libre de la plateforme lors du passage à « Vérifiée » ou « À corriger »."),
    )
    verifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Vérifiée par'),
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name='informations_primaires_verifiees',
        help_text=_("Administrateur de PLATEFORME (schéma public) — jamais un administrateur de tenant, voir TenantScopedAdminMixin."),
    )
    verifie_le = models.DateTimeField(_('Vérifiée le'), null=True, blank=True)

    # Champs comptant pour `pourcentage_completion` — volontairement une
    # liste, jamais stockée en base : toujours en phase avec les champs
    # réels du modèle, sans valeur à resynchroniser.
    CHAMPS_COMPLETION = (
        'forme_juridique', 'secteur_activite', 'raison_sociale', 'numero_rccm', 'numero_nif',
        'date_creation_ou_agrement', 'adresse_siege', 'ville', 'province', 'telephone_principal',
        'email_contact', 'responsable_nom_complet', 'responsable_fonction', 'responsable_telephone',
        'responsable_email', 'effectif_estime', 'description_activites',
    )

    class Meta:
        verbose_name = _('Informations primaires du tenant')
        verbose_name_plural = _('Informations primaires des tenants')
        ordering = ['-modifie_le']

    def __str__(self):
        return f"Informations primaires — {self.tenant.name}"

    @property
    def pourcentage_completion(self):
        """% de champs-clé renseignés — indicatif pour la plateforme
        (priorisation de la relance) et pour le tenant (ce qu'il lui
        reste à fournir)."""
        total = len(self.CHAMPS_COMPLETION)
        if not total:
            return 0
        remplis = sum(
            1 for champ in self.CHAMPS_COMPLETION
            if getattr(self, champ, None) not in (None, '')
        )
        return round((remplis / total) * 100)


class PeriodiciteDocument(models.TextChoices):
    """Périodicité d'un type de document requis — voir
    `ContraintesDocumentRequis` ci-dessous."""
    PERMANENT = 'permanent', _('Permanent (fourni une seule fois)')
    ANNUELLE = 'annuelle', _('Périodique — annuelle')
    PONCTUELLE = 'ponctuelle', _('Ponctuelle — période libre')


class TypeDocumentRequis(models.TextChoices):
    """
    Catalogue FIXE des documents que la plateforme demande à un tenant —
    volontairement câblé ici en dur (TextChoices), et non dans une table
    de paramétrage éditable : voir `ContraintesDocumentRequis` juste en
    dessous, qui associe à chaque valeur ses contraintes (taille,
    formats, périodicité). Ajouter un type = ajouter UNE valeur ici + UNE
    entrée dans `ContraintesDocumentRequis.PAR_TYPE`, sans aucune
    migration de base de données (le champ `type` de
    `TenantDocumentRequis` reste un simple CharField à choix — étendre
    les choix d'un CharField ne modifie pas le schéma SQL).
    """
    STATUTS_OU_ACTE_CONSTITUTIF = 'statuts_acte_constitutif', _('Statuts / Acte constitutif')
    EXTRAIT_RCCM = 'extrait_rccm', _('Extrait RCCM')
    ATTESTATION_NIF = 'attestation_nif', _('Attestation NIF')
    RECEPISSE_OU_AGREMENT = 'recepisse_agrement', _('Récépissé de déclaration / Agrément')
    PIECE_IDENTITE_RESPONSABLE = 'piece_identite_responsable', _("Pièce d'identité du responsable légal")
    ORGANIGRAMME = 'organigramme', _('Organigramme')
    LOGO_HAUTE_DEFINITION = 'logo_haute_definition', _('Logo en haute définition')
    FEUILLE_DE_ROUTE_ANNUELLE = 'feuille_de_route_annuelle', _('Feuille de route annuelle')
    RAPPORT_ACTIVITE_ANNUEL = 'rapport_activite_annuel', _("Rapport d'activité annuel")
    ETATS_FINANCIERS_ANNUELS = 'etats_financiers_annuels', _('États financiers annuels')


class ContraintesDocumentRequis:
    """
    Contraintes FIXES par type de document requis (voir docstring de
    `TypeDocumentRequis`). Volontairement un simple dict Python et non un
    modèle : ces contraintes sont un choix de PLATEFORME, pas une donnée
    métier éditable au jour le jour — les faire évoluer est un
    changement de code, versionné et revu comme n'importe quel autre.
    """
    DEFAUT = {
        'extensions_autorisees': ['.pdf'],
        'taille_max_mo': 5,
        'periodicite': PeriodiciteDocument.PERMANENT,
    }

    PAR_TYPE = {
        TypeDocumentRequis.STATUTS_OU_ACTE_CONSTITUTIF: {
            'extensions_autorisees': ['.pdf'], 'taille_max_mo': 5,
            'periodicite': PeriodiciteDocument.PERMANENT,
        },
        TypeDocumentRequis.EXTRAIT_RCCM: {
            'extensions_autorisees': ['.pdf'], 'taille_max_mo': 5,
            'periodicite': PeriodiciteDocument.PERMANENT,
        },
        TypeDocumentRequis.ATTESTATION_NIF: {
            'extensions_autorisees': ['.pdf'], 'taille_max_mo': 5,
            'periodicite': PeriodiciteDocument.PERMANENT,
        },
        TypeDocumentRequis.RECEPISSE_OU_AGREMENT: {
            'extensions_autorisees': ['.pdf'], 'taille_max_mo': 5,
            'periodicite': PeriodiciteDocument.PERMANENT,
        },
        TypeDocumentRequis.PIECE_IDENTITE_RESPONSABLE: {
            'extensions_autorisees': ['.pdf', '.jpg', '.jpeg', '.png'], 'taille_max_mo': 3,
            'periodicite': PeriodiciteDocument.PERMANENT,
        },
        TypeDocumentRequis.ORGANIGRAMME: {
            'extensions_autorisees': ['.pdf', '.png', '.jpg', '.jpeg'], 'taille_max_mo': 5,
            'periodicite': PeriodiciteDocument.PERMANENT,
        },
        TypeDocumentRequis.LOGO_HAUTE_DEFINITION: {
            'extensions_autorisees': ['.png', '.jpg', '.jpeg', '.svg'], 'taille_max_mo': 2,
            'periodicite': PeriodiciteDocument.PERMANENT,
        },
        TypeDocumentRequis.FEUILLE_DE_ROUTE_ANNUELLE: {
            'extensions_autorisees': ['.pdf', '.doc', '.docx'], 'taille_max_mo': 10,
            'periodicite': PeriodiciteDocument.ANNUELLE,
        },
        TypeDocumentRequis.RAPPORT_ACTIVITE_ANNUEL: {
            'extensions_autorisees': ['.pdf', '.doc', '.docx'], 'taille_max_mo': 10,
            'periodicite': PeriodiciteDocument.ANNUELLE,
        },
        TypeDocumentRequis.ETATS_FINANCIERS_ANNUELS: {
            'extensions_autorisees': ['.pdf', '.xls', '.xlsx'], 'taille_max_mo': 10,
            'periodicite': PeriodiciteDocument.ANNUELLE,
        },
    }

    @classmethod
    def pour(cls, type_document):
        return cls.PAR_TYPE.get(type_document, cls.DEFAUT)


class StatutValidationDocument(models.TextChoices):
    """Cycle de vie MÉTIER partagé par `TenantDocumentRequis` et
    `TenantDocumentGenerique`, qui redéfinissent `statut` — même principe
    que `StatutVerificationIdentite` ci-dessus."""
    EN_ATTENTE = 'en_attente', _('En attente de vérification')
    VALIDE = 'valide', _('Validé')
    REJETE = 'rejete', _('Rejeté — à corriger')
    EXPIRE = 'expire', _('Expiré')


def valider_fichier_selon_contraintes(fichier, contraintes):
    """Validateur partagé par `TenantDocumentRequis` et
    `TenantDocumentGenerique` — a besoin de connaître les contraintes
    (variables selon le type pour le premier, fixes pour le second), donc
    appelé explicitement depuis `clean()` plutôt qu'enregistré comme
    `validators=[...]` sur le champ (qui ne reçoit jamais que la valeur
    du champ, jamais le type courant de l'instance)."""
    if not fichier:
        return
    extension = os.path.splitext(getattr(fichier, 'name', '') or '')[1].lower()
    extensions_autorisees = contraintes.get('extensions_autorisees') or []
    if extensions_autorisees and extension not in extensions_autorisees:
        raise ValidationError(
            _("Format « %(ext)s » non autorisé pour ce document. Formats acceptés : %(formats)s.") % {
                'ext': extension or '?', 'formats': ', '.join(extensions_autorisees),
            }
        )
    taille_max_mo = contraintes.get('taille_max_mo')
    try:
        taille = fichier.size
    except (OSError, ValueError):
        taille = None
    if taille_max_mo and taille and taille > taille_max_mo * 1024 * 1024:
        raise ValidationError(
            _("Fichier trop volumineux (%(taille).1f Mo) — maximum %(max)s Mo pour ce document.") % {
                'taille': taille / (1024 * 1024), 'max': taille_max_mo,
            }
        )


class TenantDocumentRequis(SocleTracabilite, PeriodeValiditeMixin):
    """
    Une soumission, par un tenant, d'un type de document du catalogue
    FIXE (`TypeDocumentRequis`). Plusieurs lignes possibles pour un même
    (tenant, type) — notamment pour les types PÉRIODIQUES (ex: feuille de
    route annuelle : une ligne par année, distinguée par
    `valide_du`/`valide_au`, voir `PeriodeValiditeMixin`) ; pour un type
    PERMANENT, une soumission qui corrige/remplace la précédente se fait
    elle aussi par une NOUVELLE ligne (jamais d'écrasement — le Socle de
    Traçabilité interdit toute suppression physique), la plus récente
    (`cree_le` décroissant) faisant foi.
    """
    statut = models.CharField(
        _('Statut de validation'), max_length=30,
        choices=StatutValidationDocument.choices,
        default=StatutValidationDocument.EN_ATTENTE, db_index=True,
    )

    tenant = models.ForeignKey(
        Tenant, verbose_name=_('Tenant'), on_delete=models.CASCADE,
        related_name='documents_requis',
    )
    type = models.CharField(_('Type de document'), max_length=50, choices=TypeDocumentRequis.choices)
    fichier = models.FileField(_('Fichier'), upload_to='tenants/documents_requis/', storage=get_raw_media_storage)
    nom_fichier_original = models.CharField(_('Nom du fichier original'), max_length=255, blank=True, editable=False)
    taille = models.PositiveIntegerField(_('Taille (octets)'), default=0, editable=False)
    type_mime = models.CharField(_('Type MIME'), max_length=100, blank=True, editable=False)
    commentaire_soumission = models.TextField(
        _('Commentaire du tenant'), blank=True,
        help_text=_("Précision libre apportée par le tenant à la soumission (contexte, référence...)."),
    )
    motif_rejet = models.TextField(
        _('Motif de rejet'), blank=True,
        help_text=_("Renseigné par la plateforme si le statut passe à « Rejeté »."),
    )
    verifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Vérifié par'),
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name='documents_requis_verifies',
        help_text=_("Administrateur de PLATEFORME (schéma public), voir TenantInformationsPrimaires.verifie_par."),
    )
    verifie_le = models.DateTimeField(_('Vérifié le'), null=True, blank=True)

    class Meta:
        verbose_name = _('Document requis (tenant)')
        verbose_name_plural = _('Documents requis (tenants)')
        ordering = ['-cree_le']
        indexes = [models.Index(fields=['tenant', 'type'])]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'type', 'valide_du', 'valide_au'],
                name='unique_tenant_document_requis_par_periode',
            ),
        ]

    def __str__(self):
        return f"{self.get_type_display()} — {self.tenant.name}"

    @property
    def contraintes(self):
        return ContraintesDocumentRequis.pour(self.type)

    @property
    def est_periodique(self):
        return self.contraintes.get('periodicite') != PeriodiciteDocument.PERMANENT

    def clean(self):
        super().clean()
        if self.type and self.est_periodique and not self.valide_du:
            raise ValidationError({
                'valide_du': _('Ce type de document est périodique : la période couverte (Valide du) est obligatoire.'),
            })
        if self.fichier:
            valider_fichier_selon_contraintes(self.fichier, self.contraintes)

    def save(self, *args, **kwargs):
        if self.fichier:
            try:
                self.taille = self.fichier.size
            except (OSError, ValueError):
                pass
            if not self.nom_fichier_original:
                self.nom_fichier_original = os.path.basename(getattr(self.fichier, 'name', '') or '')
        super().save(*args, **kwargs)


class TenantDocumentGenerique(SocleTracabilite, PeriodeValiditeMixin):
    """
    Dépôt de document totalement LIBRE, sans catalogue fixe — pour tout
    ce que `TenantDocumentRequis`/`TypeDocumentRequis` n'a pas anticipé
    (besoin ponctuel, document utile au tenant sans être exigé par la
    plateforme, oubli dans le catalogue fixe...). Les contraintes de
    taille/format (`CONTRAINTES_GENERIQUES` ci-dessous) restent
    volontairement plus larges qu'un type précis de `TenantDocumentRequis`,
    faute de connaître à l'avance la nature du fichier.
    `valide_du`/`valide_au` (voir `PeriodeValiditeMixin`) couvrent le même
    besoin de période que sur `TenantDocumentRequis` (document
    périodique/temporaire) — laissés vides pour un document permanent.
    """
    statut = models.CharField(
        _('Statut de validation'), max_length=30,
        choices=StatutValidationDocument.choices,
        default=StatutValidationDocument.EN_ATTENTE, db_index=True,
    )

    tenant = models.ForeignKey(
        Tenant, verbose_name=_('Tenant'), on_delete=models.CASCADE,
        related_name='documents_generiques',
    )
    nom = models.CharField(_('Nom du document'), max_length=255, help_text=_("Titre libre, ex: « Convention de partenariat 2026 »."))
    type_libre = models.CharField(
        _('Type / catégorie'), max_length=100, blank=True,
        help_text=_("Catégorie libre indiquée par le tenant — aucune liste fixe, sert uniquement à trier/rechercher."),
    )
    description = models.TextField(_('Description'), blank=True)
    fichier = models.FileField(_('Fichier'), upload_to='tenants/documents_generiques/', storage=get_raw_media_storage)
    nom_fichier_original = models.CharField(_('Nom du fichier original'), max_length=255, blank=True, editable=False)
    taille = models.PositiveIntegerField(_('Taille (octets)'), default=0, editable=False)
    type_mime = models.CharField(_('Type MIME'), max_length=100, blank=True, editable=False)

    CONTRAINTES_GENERIQUES = {
        'extensions_autorisees': [
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.jpg', '.jpeg', '.png', '.zip',
        ],
        'taille_max_mo': 20,
    }

    class Meta:
        verbose_name = _('Document générique (tenant)')
        verbose_name_plural = _('Documents génériques (tenants)')
        ordering = ['-cree_le']
        indexes = [models.Index(fields=['tenant', 'type_libre'])]

    def __str__(self):
        return f"{self.nom} — {self.tenant.name}"

    def clean(self):
        super().clean()
        if self.fichier:
            valider_fichier_selon_contraintes(self.fichier, self.CONTRAINTES_GENERIQUES)

    def save(self, *args, **kwargs):
        if self.fichier:
            try:
                self.taille = self.fichier.size
            except (OSError, ValueError):
                pass
            if not self.nom_fichier_original:
                self.nom_fichier_original = os.path.basename(getattr(self.fichier, 'name', '') or '')
        super().save(*args, **kwargs)


