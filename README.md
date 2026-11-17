# Station météo IoT : stockage des mesures dans MongoDB

Projet de cours IoT : un capteur météo envoie ses mesures via une API, un collecteur Python les récupère et les enregistre dans une base **MongoDB Atlas**. Ces données alimentent ensuite le site météo.

> **Principe :** une mesure du capteur = un document de la collection `mesures`, avec les noms et les types définis dans le dictionnaire de données.

---

## Sommaire

1. [Architecture](#architecture)
2. [MongoDB en bref (comparaison avec SQL)](#mongodb-en-bref)
3. [Prérequis](#prérequis)
4. [Installation](#installation)
5. [Configuration d'Atlas](#configuration-datlas)
6. [Structure d'une mesure](#structure-dune-mesure)
7. [Utilisation des scripts](#utilisation-des-scripts)
8. [Contrôle des mesures et journaux](#contrôle-des-mesures-et-journaux)
9. [Arborescence du dépôt](#arborescence-du-dépôt)
10. [Sécurité](#sécurité)
11. [Auteurs](#auteurs)

---

## Architecture

```
┌──────────────────┐  MQTT  ┌──────────────────┐  PyMongo  ┌───────────────────────────┐
│ Capteur météo    │ ─────► │  mqtt_meteo.py   │ ────────► │ MongoDB Atlas (cluster M0)│
└──────────────────┘        │  (collecteur)    │           │  base : station_meteo     │
                            │        │         │           │   ├─ mesures              │
                            │  mesure.py       │           │   └─ journaux (rejets)    │
                            │  convertir()     │           │                           │
┌──────────────────┐        │        │         │           │                           │
│releves_meteo.json│ ─────► │  importer.py     │ ────────► │                           │
└──────────────────┘        └──────────────────┘           └─────────────┬─────────────┘
                              base.py : connexion() / preparer()         │
                                                         requetes.py / site météo
```

## MongoDB en bref

| Notion MongoDB | Équivalent SQL | Dans ce projet |
|---|---|---|
| **Base** (database) | Base / schéma | `station_meteo` |
| **Collection** | Table | `mesures`, `journaux` |
| **Document** (BSON, proche du JSON) | Ligne | Une mesure du capteur |
| **Champ** | Colonne | `referencecapteur`, `instantmesure`, … |
| **Index unique** | Contrainte `UNIQUE` | (`referencecapteur`, `instantmesure`) |

**Différences principales avec une base SQL :**
- **Pas de schéma imposé :** deux documents d'une même collection peuvent avoir des champs différents. C'est souple, mais la cohérence des données devient notre responsabilité, d'où le contrôle des mesures avant insertion.
- **Pas de jointures classiques :** les données utiles ensemble sont rangées dans le même document.
- **Des types riches :** dates (`datetime`), nombres, sous-documents et tableaux sont stockés tels quels.
- **Pas de `CREATE TABLE` :** une base ou une collection est créée automatiquement à la première insertion.

## Prérequis

- Python 3.10 ou plus récent
- Un compte [MongoDB Atlas](https://www.mongodb.com/atlas) avec accès au cluster du binôme
- Git

## Installation

```bash
# 1. Cloner le dépôt
git clone <url-du-depot>
cd <nom-du-depot>

# 2. Créer et activer un environnement virtuel
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt  # ou : pip install pymongo python-dotenv paho-mqtt

# 4. Créer le fichier .env à partir du modèle
cp .env.example .env
```

Contenu du fichier `.env` (**jamais commité** : il figure dans `.gitignore`) :

```env
MONGODB_URI=mongodb+srv://<utilisateur>:<mot_de_passe>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=station_meteo
```

Le code lit la chaîne de connexion sans jamais contenir le mot de passe :

```python
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
client = MongoClient(os.environ["MONGODB_URI"])
db = client[os.getenv("MONGODB_DB", "station_meteo")]
```

## Configuration d'Atlas

1. Créer un **cluster gratuit M0** (un seul par binôme) et y inviter son binôme (*Project → Access Manager*).
2. **Database Access :** créer un utilisateur de base dédié au projet, avec les droits `readWrite` limités à `station_meteo`. Ne pas utiliser le compte administrateur.
3. **Network Access :** n'autoriser que les adresses IP nécessaires (poste de chaque membre, réseau de l'école). Éviter `0.0.0.0/0`.
4. Récupérer la chaîne de connexion (*Connect → Drivers → Python*) et la coller dans `.env`.

## Structure d'une mesure

Exemple de document stocké dans `mesures`. Les champs autres que `referencecapteur` et `instantmesure` sont **à adapter selon notre dictionnaire de données** :

```json
{
  "_id": { "$oid": "..." },
  "referencecapteur": "STATION-01",
  "instantmesure": { "$date": "2026-11-17T09:00:00Z" },
  "temperature": 12.4,
  "humidite": 78,
  "pression": 1013.2,
  "vitessevent": 18.5
}
```

| Champ | Type MongoDB | Unité | Obligatoire | Plage autorisée |
|---|---|---|---|---|
| `referencecapteur` | string | – | oui | non vide |
| `instantmesure` | date (UTC) | – | oui | pas dans le futur |
| `temperature` | double | °C | oui | -40 à 60 |
| `humidite` | double / int | % | non | 0 à 100 |
| `pression` | double | hPa | non | 870 à 1085 |
| `vitessevent` | double | km/h | non | 0 à 250 |

**Conversions faites à l'import :** la date (texte) devient un `datetime` UTC, et les valeurs (souvent du texte dans le JSON) deviennent des nombres.

**Index unique :** un capteur ne peut pas produire deux mesures au même instant.

```python
db.mesures.create_index(
    [("referencecapteur", 1), ("instantmesure", 1)],
    unique=True,
    name="unicite_capteur_instant",
)
```

## Utilisation des scripts

### `base.py` : connexion et préparation de la base

- `connexion()` lit `MONGODB_URI` dans `.env` et renvoie la base `station_meteo`.
- `preparer(db)` crée l'index unique sur (`referencecapteur`, `instantmesure`). L'opération est sans effet si l'index existe déjà.

### `mesure.py` : nettoyage d'une mesure

`convertir(donnee_brute)` transforme une mesure brute en document propre : la date devient un `datetime` UTC, les valeurs deviennent des nombres et les noms suivent le dictionnaire de données. Cette fonction est partagée par `importer.py` et `mqtt_meteo.py`.

### `importer.py` : import du fichier JSON

```bash
python importer.py
```

Le script lit `releves_meteo.json`.

Pour chaque mesure du fichier, le script :
1. la convertit (date en `datetime` UTC, valeurs en nombres) ;
2. la contrôle selon les règles du dictionnaire ;
3. l'insère si elle est valide, ou trace le rejet dans `journaux` dans le cas contraire ;
4. ignore les doublons (erreur `DuplicateKeyError` interceptée grâce à l'index unique).

Un résumé s'affiche à la fin, par exemple : `120 lues, 115 insérées, 3 doublons, 2 rejetées`.

> Le script peut être relancé sans risque : grâce à l'index unique, une deuxième exécution n'ajoute aucun doublon.

### `requetes.py` : requêtes de consultation

```bash
python requetes.py
```

| Requête | Méthode PyMongo |
|---|---|
| Dernière mesure reçue | `find_one(sort=[("instantmesure", -1)])` |
| Mesures des dernières 24 h | `find({"instantmesure": {"$gte": maintenant - timedelta(hours=24)}})` |
| Nombre de mesures | `count_documents({})` |
| Mesures au-dessus de 30 °C | `find({"temperature": {"$gt": 30}})` |
| Cinq plus fortes vitesses de vent | `find().sort("vitessevent", -1).limit(5)` |

### `mqtt_meteo.py` : collecte en continu (MQTT)

```bash
python mqtt_meteo.py
```

Le collecteur s'abonne au topic MQTT du capteur avec `paho-mqtt`. À chaque message reçu, il **réutilise `convertir()` (mesure.py) et `connexion()` (base.py)** pour insérer la nouvelle mesure dans MongoDB. La logique n'est ainsi écrite qu'une fois.

### `essais.py` : entraînement au CRUD

Script de l'étape 6 : `insert_one`, `find`, `update_one` et `delete_one` sur une collection `essais`, supprimée à la fin.

## Contrôle des mesures et journaux

Avant insertion, chaque mesure est vérifiée :
- **champs obligatoires** présents et non vides ;
- **types** corrects après conversion ;
- **valeurs** comprises dans les plages du dictionnaire.

Une mesure invalide n'est **pas insérée** dans `mesures`. Elle est tracée dans la collection `journaux` :

```json
{
  "instant": { "$date": "2026-11-17T09:05:12Z" },
  "source": "importer.py",
  "motif": "temperature hors plage (-40 à 60) : 152.0",
  "mesure": { "referencecapteur": "STATION-01", "temperature": "152" }
}
```

Le fichier `tests/mesures_invalides.json` contient des mesures volontairement fausses, écrites par le binôme (champ manquant, date illisible, température aberrante, doublon…), pour vérifier ce comportement :

```bash
python importer.py   # après avoir remplacé le fichier lu par tests/mesures_invalides.json
```

## Arborescence du dépôt

```
.
├── README.md
├── requirements.txt
├── .env.example          # modèle de configuration (sans secret)
├── .gitignore            # contient .env, .venv/, __pycache__/, .idea/
├── base.py               # connexion() et preparer() : connexion Atlas et index unique
├── mesure.py             # convertir() : nettoyage d'une mesure brute
├── importer.py           # import de releves_meteo.json
├── mqtt_meteo.py         # collecteur MQTT, insertion en continu
├── essais.py             # entraînement au CRUD (étape 6)
├── requetes.py           # requêtes de consultation
├── releves_meteo.json    # données d'exemple du capteur
└── tests/
    └── mesures_invalides.json
```

## Sécurité

- Le mot de passe ne figure **jamais** dans le code ni dans Git : il est lu depuis `.env`, lui-même exclu par `.gitignore`.
- Un utilisateur de base dédié, avec des droits limités.
- La liste des adresses IP autorisées est restreinte sur Atlas.
- En cas de fuite de `.env`, changer immédiatement le mot de passe dans *Database Access*.

## Auteurs

- Pauline
- Agathe













1. Où est la valeur dans le JSON ?

2. Quel est le nom attendu dans le dictionnaire MongoDB ?

3. Quel est le type attendu ?

4. Faut-il convertir ?




| releves.meteo.JSON | Dans le dictionnaire | Type attendu | Conversion en Python |
| :--- | :--- | :--- | :--- |
| *(Manquant, à ajouter)* | `reference_capteur` | Texte | Aucune |
| *(Manquant, à ajouter)* | `instant_mesure` | Date UTC | Texte vers Date UTC |
| `"Air Temperature"` | `temperature` | Décimal | Enlever " ℃", vers `float` |
| `"Air Humidity"` | `humidite` | Décimal | Enlever " % RH", vers `float` |
| `"Wind Speed"` | `vent_vitesse` | Décimal | Enlever " m/s", vers `float` |
| `"Wind Direction"` | `vent_direction` | Entier | Enlever " °", vers `int` |
| `"Rainfall Intensity"` | `precipitation` | Décimal | Enlever " mm/hour", vers `float` |
| `"Cumulative Rainfall"`| `pluie_cumul` | Décimal | Enlever " mm", vers `float` |
| `"Light Intensity"` | `luminosite` | Entier | Enlever " Lux", vers `int` |
| `"UV Index"` | `indice_uv` | Décimal | Enlever " UV", vers `float` |
| `"Barometric Pressure"`| `pression_atmospherique` | Décimal | Enlever "Pa", vers `float` |
| *(Manquant)* | `qualite_signal` | Entier | - |
| *(Manquant)* | `payload_brut` | Texte | - |