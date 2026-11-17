import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

# Se connecte à Atlas et renvoie la base station_meteo.
def connexion():
   
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    
    if not uri:
        sys.exit("MONGODB_URI est absente du fichier .env")
        
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except PyMongoError as erreur:
        sys.exit(f"Connexion impossible. Vérifier l'adresse IP autorisée, "
                 f"l'utilisateur et le mot de passe.\nDétail : {erreur}")
                 
    return client[os.getenv("MONGODB_BASE", "station_meteo")]

# Créer l'index unique pour empêcher les doublons.
def preparer(db):
  
    db.mesures.create_index(
        [("reference_capteur", ASCENDING), ("instant_mesure", ASCENDING)],
        unique=True
    )

if __name__ == "__main__":
    db = connexion()
    print("Connecté à la base", db.name)