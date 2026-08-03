def get_token_settings():
    """
    Récupère les paramètres de token depuis la base de données
    Retourne None si aucun paramètre personnalisé n'est défini
    """
    try:
        from django.apps import apps
        from django.db.utils import OperationalError, ProgrammingError
        
        # Vérifier que l'application est installée
        if not apps.is_installed('token_manager'):
            print("L'application token_manager n'est pas installée")
            return None
            
        from .models import TokenSettings
        
        try:
            # Récupérer la configuration active
            token_settings = TokenSettings.objects.filter(is_active=True).first()
            
            if token_settings:
                print(f"Chargement des paramètres JWT depuis la base de données: {token_settings.name}")
                return token_settings.to_jwt_settings()
            else:
                print("Aucune configuration JWT active trouvée dans la base de données")
                return None
                
        except (OperationalError, ProgrammingError) as e:
            # En cas d'erreur de base de données (table non créée, etc.)
            print(f"Erreur lors de l'accès à la base de données: {e}")
            return None
            
    except Exception as e:
        print(f"[JWT] Erreur lors du chargement des paramètres personnalisés: {e}")
    
    return None
