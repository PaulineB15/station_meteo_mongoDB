import paho.mqtt.client as mqtt
import json
import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv

# Imports pour la BDD MongoDB
from pymongo.errors import PyMongoError
from base import connexion, preparer
from mesure import enregistrer

# Charge les variables cachées dans le fichier .env (mots de passe, adresses)
load_dotenv()


# GESTION DES ALERTES 

# Définition de la fonction d'envoi d'email
def envoyer_alerte(type_alerte, valeur, seuil):
    msg = EmailMessage()
    texte_alerte = f"L'alerte '{type_alerte}' a été déclenchée.\nValeur relevée : {valeur}\nSeuil autorisé : {seuil}"
    msg.set_content(texte_alerte)

    msg['Subject'] = f"⚠️ Alerte Météo : {type_alerte}"
    msg['From'] = os.getenv("EMAIL_SENDER")
    msg['To'] = os.getenv("EMAIL_RECEIVER")

    try:
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.starttls()
        s.login(os.getenv("EMAIL_SENDER"), os.getenv("EMAIL_PASSWORD"))
        s.send_message(msg)
        s.quit()
        print(f"Email d'alerte envoyé pour : {type_alerte}")
    except Exception as e:
        print(f"Impossible d'envoyer l'email d'alerte ({type_alerte}) : {e}")



# CONNEXION AUX SERVEURS

def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")

    client.subscribe(os.getenv("MQTT_TOPIC"))

# Connexion à MongoDB
try:
    db = connexion()
    preparer(db) # Pour les anti-doublon
except PyMongoError as e:
    print(f"Erreur de démarrage MongoDB : {e}")


def on_message(client, userdata, msg):
    print("Topic     : " + msg.topic)

    # Lit le message reçu par l'antenne
    texte_decode = msg.payload.decode("utf-8")
    donnees = json.loads(texte_decode)
    print("Données décodées :", donnees)


    # Récupère "payloadHex" (station) ou "payload" (ancien format)
    payload = donnees.get("payloadHex") or donnees.get("payload")
    if not payload:
        print("Message ignoré (pas de payload).")
        return

    # DÉCODAGE MANUEL : Découpe le payload morceau par morceau pour retrouver les vrais chiffres
    payload = payload.strip()
    if len(payload) < 40:
        print(f"Payload invalide (trop court : {len(payload)} caractères).")
        return

    try:
        # Vérifie que tous les caractères sont hexadécimaux (y compris les IDs de blocs)
        int(payload, 16)

        bloc_ID1 = payload[0:2]
        decoded_Id1 = int(bloc_ID1, 16)
        print(f"{decoded_Id1} ID")

        bloc_Temperature = payload[2:6]
        raw_temp = int(bloc_Temperature, 16)
        # Conversion entier signé 16 bits (ex. FFF2 -> -14 -> -1.4 °C)
        temp_dixiemes = raw_temp - 0x10000 if raw_temp >= 0x8000 else raw_temp
        temp_actuelle = temp_dixiemes / 10.0
        print(f"Air Temperature : {temp_actuelle} ℃")

        bloc_Humidity = payload[6:8]
        decode_Humidity = int(bloc_Humidity, 16)
        print(f"Air Humidity : {decode_Humidity} %")

        bloc_Light = payload[8:16]
        decode_Light = int(bloc_Light, 16)
        print(f"Light Intensity : {decode_Light} Lux")

        bloc_uv = payload[16:18]
        decoded_uv = int(bloc_uv, 16)
        print(f"UV Index : {decoded_uv / 10.0} UV")

        bloc_speed = payload[18:22]
        decoded_speed = int(bloc_speed, 16)
        vent_actuel = decoded_speed / 10.0
        print(f"Wind Speed : {vent_actuel} m/s")

        bloc_ID2 = payload[22:24]
        decoded_ID2 = int(bloc_ID2, 16)
        print(f"{decoded_ID2} ID")

        bloc_direction = payload[24:28]
        decoded_direction = int(bloc_direction, 16)
        print(f"Wind Direction :  {decoded_direction} °")

        bloc_rainfall = payload[28:36]
        decoded_rainfall = int(bloc_rainfall, 16)
        print(f"Rainfall Intensity : {decoded_rainfall / 1000} mm/hour")

        bloc_pressure = payload[36:40]
        decoded_pressure = int(bloc_pressure, 16)
        pression_hpa = decoded_pressure / 10.0
        print(f"Barometric Pressure : {pression_hpa} hPa")

    # Reforme un dictionnaire clair avec les unités
        donnees_decodes = {
            "Air Temperature": f"{temp_actuelle} ℃",
            "Air Humidity": f"{decode_Humidity} %",
            "Light Intensity": f"{decode_Light} Lux",
            "UV Index": f"{decoded_uv / 10.0} UV",
            "Wind Speed": f"{vent_actuel} m/s",
            "Wind Direction": f"{decoded_direction} °",
            "Rainfall Intensity": f"{decoded_rainfall / 1000} mm/hour",
            "Barometric Pressure": f"{pression_hpa} hPa",
        }

        pluie_actuelle = None
        if len(payload) >= 54:
            bloc_Id3 = payload[40:42]
            decoded_Id3 = int(bloc_Id3, 16)
            print(f"{decoded_Id3} ID")

            bloc_peak = payload[42:46]
            decoded_peak = int(bloc_peak, 16)
            print(f"Peak Wind Gust : {decoded_peak / 10.0} m/s")

            bloc_cumulative_rainfall = payload[46:54]
            decoded_cumulative_rainfall = int(bloc_cumulative_rainfall, 16)
            pluie_actuelle = decoded_cumulative_rainfall / 10.0
            print(f"Cumulative Rainfall : {pluie_actuelle} mm")

            donnees_decodes["Peak Wind Gust"] = f"{decoded_peak / 10.0} m/s"
            donnees_decodes["Cumulative Rainfall"] = f"{pluie_actuelle} mm"
    except ValueError as e:
        print(f"Payload invalide ignoré : {e}")
        return

    # Récupère les seuils du .env en forçant le format décimal (float)
    seuil_chaleur = float(os.getenv("ALERTE_CHALEUR"))
    seuil_froid = float(os.getenv("ALERTE_FROID"))
    seuil_vent = float(os.getenv("ALERTE_VENT"))
    seuil_pluie = float(os.getenv("ALERTE_PLUIE"))

    # Teste les conditions et on déclenche la fonction d'envoi d'email
    if temp_actuelle >= seuil_chaleur:
        envoyer_alerte("Chaleur", temp_actuelle, seuil_chaleur)

    if temp_actuelle <= seuil_froid:
        envoyer_alerte("Froid", temp_actuelle, seuil_froid)

    if vent_actuel >= seuil_vent:
        envoyer_alerte("Vent Violent", vent_actuel, seuil_vent)

    if pluie_actuelle is not None and pluie_actuelle >= seuil_pluie:
        envoyer_alerte("Pluie Abondante", pluie_actuelle, seuil_pluie)

    with open("releves_meteo.json", "w", encoding="utf-8") as fichier:
        json.dump(donnees_decodes, fichier, indent=4, ensure_ascii=False)

    # Insertion des données dans MongoDB
    try:
        resultat_mongo = enregistrer(db, donnees_decodes)
        print(f"MongoDB : {resultat_mongo}")
    except PyMongoError as erreur:
        print(f"Erreur MongoDB pendant l'insertion : {erreur}")

mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = on_message

broker = os.getenv("MQTT_BROKER")
port = int(os.getenv("MQTT_PORT"))

mqttc.connect(broker, port, 60)
mqttc.loop_forever()