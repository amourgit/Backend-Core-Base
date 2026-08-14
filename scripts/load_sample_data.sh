#!/bin/bash

# Script de chargement des données de test pour CIVITAS NEWS
# Ce script active l'environnement virtuel et exécute le script Python de chargement

# Définir le répertoire du script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "Chargement des données de test CIVITAS NEWS"
echo "=========================================="
echo ""

# Vérifier que l'environnement virtuel existe
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "ERREUR: L'environnement virtuel n'existe pas dans $PROJECT_DIR/venv"
    exit 1
fi

# Activer l'environnement virtuel
echo "Activation de l'environnement virtuel..."
source "$PROJECT_DIR/venv/bin/activate"

# Vérifier que le fichier de données existe
DATA_FILE="$PROJECT_DIR/fixtures/sample_data.json"
if [ ! -f "$DATA_FILE" ]; then
    echo "ERREUR: Le fichier de données n'existe pas: $DATA_FILE"
    deactivate
    exit 1
fi

echo "Fichier de données trouvé: $DATA_FILE"
echo ""

# Exécuter le script Python
echo "Exécution du script de chargement..."
python "$SCRIPT_DIR/load_sample_data.py"

# Vérifier le code de retour
if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "Succès! Les données ont été chargées."
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo "ERREUR lors du chargement des données."
    echo "=========================================="
    deactivate
    exit 1
fi

# Désactiver l'environnement virtuel
deactivate

echo ""
echo "Terminé."
