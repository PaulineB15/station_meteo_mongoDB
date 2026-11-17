# Outil "timedelta": fait des calculs avec le temps (ex: reculer de 24 heures)
from datetime import timedelta
from base import connexion

# Connexion à MongoDB
db = connexion()

print("\n 1. Dernière mesure reçue ")
# find_one({}) cherche 1 seul document 
# "sort" -1 : Trie décroissant (plus grand au plus petit ou plus récent au plus ancien).
# Résultat : Dernière mesure envoyée par le capteur.
derniere = db.mesures.find_one({}, sort=[("instant_mesure", -1)])
print(derniere)

print("\n 2. Mesures des dernières 24 h ")
# Prend la date de la dernière mesure comme point de référence
if derniere and "instant_mesure" in derniere:
    # Mémorise la date exacte de cette dernière mesure
    reference = derniere["instant_mesure"]

    # Calcule l'heure qu'il était 24 heures plus tôt
    il_y_a_24h = reference - timedelta(hours=24)

    #Cherche les dates qui sont "Plus grandes ou égales" ($gte) à hier
    # ET "Plus petites" ($lt) que la référence
    filtre_24h = {"instant_mesure": {"$gte": il_y_a_24h, "$lt": reference}}

    # Compte combien de documents correspondent à ce filtre
    nb_24h = db.mesures.count_documents(filtre_24h)
    print(f"{nb_24h} mesure(s) dans les 24h précédant le dernier relevé.")

print("\n 3. Nombre total de mesures ")
# count_documents({}):  sans filtre compte tout
total = db.mesures.count_documents({})
print(f"{total} mesure(s) au total dans la base.")

print("\n 4. Mesures au-dessus de 30 °C ")
# Filtre "$gt" (greater than) - toutes les mesures où la température est > 30"
chaudes = db.mesures.find({"temperature": {"$gt": 30}})
nb_chaudes = db.mesures.count_documents({"temperature": {"$gt": 30}})

print(f"{nb_chaudes} mesure(s) trouvée(s) :")
for m in chaudes: # Boucle pour afficher les mesures trouvées une par une
    print(m)

print("\n 5. Cinq plus fortes vitesses de vent ")
# Tri décroissant sur le vent + garde seulement les 5 premiers
vents_forts = db.mesures.find({}).sort("vent_vitesse", -1).limit(5)
for m in vents_forts:
    print(m)