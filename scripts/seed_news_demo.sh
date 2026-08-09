#!/usr/bin/env bash
# ==============================================================
# scripts/seed_news_demo.sh
#
# Peuple un tenant avec des données de démonstration complètes autour
# de News (référentiels, commentaires, sondages, liens de partage) —
# voir scripts/seed_news_demo.json pour les données et
# scripts/seed_news_demo.py pour la logique de création.
#
# Usage :
#   ./scripts/seed_news_demo.sh                  # tenant auto-détecté
#                                                 # (uniquement si un
#                                                 # seul tenant actif
#                                                 # existe)
#   ./scripts/seed_news_demo.sh moncampus         # tenant explicite
#
# Ne nécessite AUCUNE intervention manuelle au préalable (pas besoin
# d'activer le venv, ni de se placer dans un dossier précis) : ce
# script se débrouille seul, où qu'il soit lancé depuis.
# ==============================================================
set -euo pipefail

# --- Localisation du projet, indépendamment du répertoire courant ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [[ ! -f "manage.py" ]]; then
    echo "❌ manage.py introuvable dans $PROJECT_ROOT — ce script doit rester dans le dossier scripts/ à la racine du projet Django." >&2
    exit 1
fi

# --- Activation du venv (si présent et pas déjà activé) ---
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    if [[ -f "venv/bin/activate" ]]; then
        echo "▶ Activation de l'environnement virtuel (venv/)..."
        # shellcheck disable=SC1091
        source "venv/bin/activate"
    elif [[ -f ".venv/bin/activate" ]]; then
        echo "▶ Activation de l'environnement virtuel (.venv/)..."
        # shellcheck disable=SC1091
        source ".venv/bin/activate"
    else
        echo "⚠️  Aucun venv/ ou .venv/ trouvé à la racine du projet — poursuite avec l'interpréteur Python courant ($(command -v python3 || command -v python))." >&2
    fi
else
    echo "▶ Environnement virtuel déjà actif : $VIRTUAL_ENV"
fi

PYTHON_BIN="$(command -v python || command -v python3)"
if [[ -z "$PYTHON_BIN" ]]; then
    echo "❌ Aucun interpréteur Python trouvé." >&2
    exit 1
fi

if ! "$PYTHON_BIN" -c "import django" 2>/dev/null; then
    echo "❌ Django n'est pas importable avec $PYTHON_BIN — vérifiez que les dépendances sont installées (pip install -r requirements.txt) dans le venv attendu." >&2
    exit 1
fi

# --- Tenant cible (argument positionnel optionnel) ---
if [[ $# -ge 1 ]]; then
    export SEED_TENANT_SCHEMA="$1"
    echo "▶ Tenant explicitement demandé : $SEED_TENANT_SCHEMA"
else
    echo "▶ Aucun tenant précisé — tentative de détection automatique (fonctionne uniquement s'il n'existe qu'un seul tenant actif)."
fi

export SEED_JSON_PATH="$SCRIPT_DIR/seed_news_demo.json"

echo "▶ Exécution du seed via 'manage.py shell'..."
echo

"$PYTHON_BIN" manage.py shell < "$SCRIPT_DIR/seed_news_demo.py"
