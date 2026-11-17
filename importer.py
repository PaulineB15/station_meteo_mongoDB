import json
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from base import connexion, preparer
from mesure import convertir, ReleveInvalide 


# Fonction: écrit dans le journal des erreurs (collection 'journaux' sur Atlas)
def journaliser(db, type_evenement, statut, message, detail=None):
    db.journaux.insert_one({
        "type_evenement": type_evenement,
        "statut": statut,
        "date_evenement": datetime.now(timezone.utc), # Heure de l'erreur
        "message": message, # Texte de l'erreur
        "detail": detail or {} # Donnée brute qui a causé le plantage
    })


# Lit le fichier JSON généré par le script MQTT
with open("releves_meteo.json", encoding="utf-8") as fichier:
    donnee_brute = json.load(fichier)

# Connexion à Atlas + envoie dans MongoDB
db = connexion()
# Créer l'index anti-doublon (Identifiant + Date) 
preparer(db)

# Inser dans la collection "mesures" de la BDD Atlas MongoDB
try:
    # Nettoyer la donnée
    document_propre = convertir(donnee_brute)
    # Insérer la donnée
    db.mesures.insert_one(document_propre)
    print("Succès : La mesure a été insérée dans Atlas.")

# Si la fonction convertir() déclenche l'alarme 
except ReleveInvalide as erreur:
    # L'alarme a sonné : on refuse la mesure et on l'écrit dans les journaux
    print(f"Rejeté : {erreur}")
    journaliser(db, "PAYLOAD_REJETE", "ECHEC", f"Relevé rejeté : {erreur}", {"releve_recu": donnee_brute})

# Si Atlas détecte que la donnée existe déjà (doublon: même identifiant + même date)    
except DuplicateKeyError:
    print("Refusé : Ce document existe déjà en base (doublon).")