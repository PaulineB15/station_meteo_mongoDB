# Fichier pour nettoyer les données avant de les envoyer à MongoDB

from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError

# Alerte pour les erreurs (donnée obligatoire manquante ou fausse)
class ReleveInvalide(Exception):
    """Exception levée quand une donnée obligatoire est invalide."""
    pass

# Copie des données limites du dico des données (pour la vérification des PLAGES)
# Cela permet de centraliser toutes les règles
PLAGES = {
    "temperature": (-40, 85),
    "humidite": (0, 100),
    "luminosite": (0, 200000),
    "indice_uv": (0, 15),
    "vent_vitesse": (0, 60),
    "vent_direction": (0, 359),
    "precipitation": (0, 240),
    "pression_atmospherique": (300, 1100),
    "rafale_max": (0, 60),
    "pluie_cumul": (0, float('inf')) 
}


# Fonction outil: Enlève l'unité de mesure et convertit le texte en nombre
# "nom_champ" - pour que la fonction sache quelle limite vérifier 
def nettoyer(texte_brut, symbole, nom_champ, entier=False):
    """Enlève l'unité et vérifie si le chiffre est dans la bonne plage."""
    # Si la donnée n'existe pas, on arrête et on renvoie "None" 
    if texte_brut is None:
        return None
    
    # .replace() - Cherche le symbole (ex: ' ℃') par du vide
    # .strip() enlève les espaces invisibles autour du chiffre
    texte_propre = str(texte_brut).replace(symbole, "").strip()

    try:
        # Transforme le texte "27.6" en vrai nombre décimal 27.6
        valeur = float(texte_propre)
        # Si un entier=True, arrondit + convertit en int(entier)
        valeur_finale = int(round(valeur)) if entier else valeur
        
        # Vérifie si la valeur respecte les limites du dico des données
        if nom_champ in PLAGES:
            minimum, maximum = PLAGES[nom_champ]
            if not (minimum <= valeur_finale <= maximum):
                return None # Si a valeur est hors limites = ne renvois rien
                
        return valeur_finale
    except ValueError:
        return None # Si donnée reçu n'est pas un nombre (ex: "Capteur cassé") = ne renvois rien


# Fonction principale : Transforme releves_meteo.json pour la BDD MongoDB
def convertir(donnees_brutes):

    # Fausse référence pour le test (16 caractères)
    reference = "TEST1234567890AB"

    # Si la référence ne fait pas 16 caractères = l'alarme
    if len(reference) != 16:
        raise ReleveInvalide(f"Identifiant capteur invalide : {reference}")

    document = {
        # Renomme selon le dictionnaire de données + nettoyer les données

        # Référence (qui fera sonner l'alarme au dessus car elle a moins de 16 caractères)
        "reference_capteur": reference,
        
        "instant_mesure": datetime.now(timezone.utc),
        
        # Données converties

        # Exemple : "Air Temperature", on enlève "℃", et on l'appelle "temperature"
        "temperature": nettoyer(donnees_brutes.get("Air Temperature"), "℃", "temperature"),
        "humidite": nettoyer(donnees_brutes.get("Air Humidity"), "% RH", "humidite"),
        "luminosite": nettoyer(donnees_brutes.get("Light Intensity"), "Lux", "luminosite", entier=True),
        "indice_uv": nettoyer(donnees_brutes.get("UV Index"), "UV", "indice_uv"),
        "vent_vitesse": nettoyer(donnees_brutes.get("Wind Speed"), "m/s", "vent_vitesse"),
        "vent_direction": nettoyer(donnees_brutes.get("Wind Direction"), "°", "vent_direction", entier=True),
        "precipitation": nettoyer(donnees_brutes.get("Rainfall Intensity"), "mm/hour", "precipitation"),
        "pression_atmospherique": nettoyer(donnees_brutes.get("Barometric Pressure"), "Pa", "pression_atmospherique"),
        "rafale_max": nettoyer(donnees_brutes.get("Peak Wind Gust"), "m/s", "rafale_max"),
        "pluie_cumul": nettoyer(donnees_brutes.get("Cumulative Rainfall"), "mm", "pluie_cumul")
    }

    # Retire les données effacées (None) pour avoir un document propre
    document_final = {k: v for k, v in document.items() if v is not None}
    return document_final


# Fonction : écrire dans le journal des erreurs (depuis importer.py)
def journaliser(db, type_evenement, statut, message, detail=None):
    db.journaux.insert_one({
        "type_evenement": type_evenement,
        "statut": statut,
        "date_evenement": datetime.now(timezone.utc),
        "message": message,
        "detail": detail or {}
    })

    


# Fonction - appelée à chaque fois que l'antenne MQTT reçoit une donnée en temps réel
# Nettoie la donnée, l'enregistre dans Atlas + gère les erreurs ou les doublons.
def enregistrer(db, donnees_brutes):
    """Contrôle et insère une mesure. Renvoie 'inseree', 'doublon' ou 'rejetee'."""
    try:
        document_propre = convertir(donnees_brutes)
        db.mesures.insert_one(document_propre)
        return "inseree"
    except ReleveInvalide as erreur:
        journaliser(db, "PAYLOAD_REJETE", "ECHEC", f"Relevé rejeté : {erreur}", {"releve_recu": donnees_brutes})
        return "rejetee"
    except DuplicateKeyError:
        return "doublon"
    
    