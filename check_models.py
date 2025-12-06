import requests
from datetime import datetime
import google.generativeai as genai
import os
import json
import difflib

# Configuration Gemini
os.environ["GOOGLE_API_KEY"] = "AIzaSyBDQjWtTne9MDlPVE8Ky9-5g34wAGqTRBI"
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
    "Accept": "application/json",
    "Referer": "https://alloeu-basket-club.sporteasy.net/",
    "Origin": "https://alloeu-basket-club.sporteasy.net",
    "x-csrftoken": "WzwU5QNlQTysEJNOww2NACxltnk4mXs5",
    "Cookie": (
        "se_csrftoken=WzwU5QNlQTysEJNOww2NACxltnk4mXs5; "
        "didomi_token=eyJ1c2VyX2lkIjoiMTk3OWNjMTctYTJmMS02NDhjLWJiNTctNTc1NjZhNmJkNDA2IiwiY3JlYXRlZCI6IjIwMjUtMDYtMjNUMTI6MjY6NTQuODk1WiIsInVwZGF0ZWQiOiIyMDI1LTA2LTIzVDEyOjI3OjM5LjY3OVoiLCJ2ZXJzaW9uIjoyLCJ2ZW5kb3JzIjp7ImVuYWJsZWQiOlsiZ29vZ2xlIiwiYzpnb29nbGVhbmEtNFRYbkppZ1IiLCJjOmxpbmtlZGluLW1hcmtldGluZy1zb2x1dGlvbnMiLCJjOmh1YnNwb3QiLCJjOmFtcGxpdHVkZSIsImM6eW91dHViZSIsImM6aG90amFyIiwiYzpuZXctcmVsaWMiLCJjOmh1YnNwb3QtZm9ybXMiLCJjOmxpbmtlZGluIl19LCJ2ZW5kb3JzX2xpIjp7ImVuYWJsZWQiOlsiZ29vZ2xlIl19LCJhYyI6IkFGbUFDQUZrLkFGbUFDQUZrIn0=; "
        "euconsent-v2=CQTdfoAQTdfoAAHABBENBvFgAP_AAELAAAqIGSQAgF5gMkAySAEAvMBkgAAA.f_gACFgAAAAA; "
        "se_last_url=\"/fr/notifications/\"; "
        "se_referer=\"https://www.google.com/\"; "
        "sporteasy=cbn86tfo3psuoz0bcuvjipcf2bkkrvc1; "
        "se_first_url=\"/fr/notifications/\""
    )
}

def requete_matchs_SE(url):
    print("⏳ Envoi de la requête...")
    response = requests.get(url, headers=HEADERS)


    if response.status_code != 200:
        print(f"❌ Échec. Code : {response.status_code}")
        print("Réponse du serveur :")
        print(response.text)
        return None

    else:
        print("✅ Succès ! Connexion établie.")
        return response

def analyser_match_basket(chemin_fichier, nom_club_cible="ALLOEU BASKET CLUB"):
    """
    Envoie le fichier à Gemini et extrait les stats spécifiques pour le club cible.
    """
    
    # 1. Le Prompt : C'est ici qu'on donne l'intelligence au script
    prompt = f"""
    Tu es un assistant expert en statistiques de basket. Analyse ce document qui contient les feuilles de match.
    
    Tâche 1 : Identification des équipes
    - Regarde en haut du document pour identifier qui est "Équipe A" et qui est "Équipe B".
    - Le premier tableau de données correspond à l'Équipe A (Locaux).
    - Le deuxième tableau de données correspond à l'Équipe B (Visiteurs).
    
    Tâche 2 : Extraction des scores
    - Trouve le score final pour chaque équipe (Ligne "Total Équipe").
    - Trouve le score par mi-temps pour chaque équipe (Lignes "Total 1ère..." et "Total 2ème...").

    Tâche 3 : Statistiques des joueurs de "{nom_club_cible}"
    - Identifie quel tableau correspond à ce club.
    - Pour chaque joueur de ce club, extrais :
      - Nom
      - Temps de jeu
      - 3 Pts Réussis
      - 2 Pts Réussis (ATTENTION : Tu dois additionner "2 Int Réussis" et "2 Ext Réussis")
      - LF Réussis
      - Fautes Commises (Ftes Com)

    Format de réponse attendu : 
    Réponds UNIQUEMENT avec un objet JSON valide (sans Markdown ```json) suivant cette structure :
    {{
      "match_info": {{
        "equipe_A": "Nom",
        "equipe_B": "Nom",
        "score_A_final": 0,
        "score_B_final": 0,
        "score_A_mitemps": [0, 0],
        "score_B_mitemps": [0, 0]
      }},
      "stats_club_cible": [
        {{
          "joueur": "Nom Prénom",
          "tps_jeu": "MM:SS",
          "3_pts": 0,
          "2_pts_total": 0,
          "lf": 0,
          "fautes": 0
        }}
      ]
    }}
    """

    # 2. Envoi du fichier (Texte brut ou PDF)
    # Si ton fichier est un PDF sur le disque :
    mon_fichier = genai.upload_file(chemin_fichier, mime_type="application/pdf")
    
    # 3. Génération de la réponse
    print(f"Analyse du match pour {nom_club_cible} en cours...")
    response = model.generate_content([mon_fichier, prompt])
    
    # 4. Nettoyage et parsing JSON
    try:
        # On nettoie les éventuelles balises markdown si le modèle en met
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_text)
        return data
    except json.JSONDecodeError:
        print("Erreur : La réponse n'est pas un JSON valide.")
        print(response.text)
        return None

def convert_time(time_str):
    if not time_str or time_str == "00:00":
        return 0
    try:
        parts = time_str.split(':')
        minutes = int(parts[0])
        seconds = int(parts[1])
        if seconds >= 30:
            minutes += 1
        return minutes
    except:
        return 0

def match_players(gemini_stats, se_players):
    mapping = {}
    for g_player in gemini_stats:
        g_name = g_player['joueur'].lower()
        best_match = None
        best_score = 0
        
        for se_player in se_players:
            profile = se_player['profile']
            full_name = f"{profile['last_name']} {profile['first_name']}".lower()
            full_name_rev = f"{profile['first_name']} {profile['last_name']}".lower()
            
            # Simple containment check first
            if profile['last_name'].lower() in g_name and profile['first_name'].lower() in g_name:
                best_match = se_player
                best_score = 100
                break
            
            # Fuzzy match
            score1 = difflib.SequenceMatcher(None, g_name, full_name).ratio()
            score2 = difflib.SequenceMatcher(None, g_name, full_name_rev).ratio()
            score = max(score1, score2)
            
            if score > best_score and score > 0.6: # Threshold
                best_score = score
                best_match = se_player
        
        if best_match:
            mapping[str(best_match['profile']['id'])] = g_player
            print(f"✅ Match: {g_player['joueur']} -> {best_match['profile']['full_name']}")
        else:
            print(f"⚠️ Pas de correspondance pour: {g_player['joueur']}")
            
    return mapping

def update_event_stats(event, pdf_path):
    # 1. Analyze PDF
    club_name = "ALLOEU BASKET CLUB" 
    
    stats_data = analyser_match_basket(pdf_path, club_name)
    if not stats_data:
        return

    team_id = event['opponent_right']['id'] if event['opponent_right']['is_current_team'] else event['opponent_left']['id']
    event_id = event['id']
    
    # 2. Get Players
    url_players = f"https://api.sporteasy.net/v2.1/teams/{team_id}/events/{event_id}/stats/players/"
    print(f"Récupération des joueurs: {url_players}")
    resp_players = requests.get(url_players, headers=HEADERS)
    if resp_players.status_code != 200:
        print("Erreur récupération joueurs")
        return
    
    se_players = resp_players.json()['players']
    
    # 3. Map Players
    player_mapping = match_players(stats_data['stats_club_cible'], se_players)
    
    # 4. Prepare Player PUT Payload
    payload_players = {}
    for pid, g_stats in player_mapping.items():
        payload_players[pid] = {
            "basket_player_free_throws": g_stats['lf'],
            "basket_player_two_point_goals": g_stats['2_pts_total'],
            "basket_player_three_point_goals": g_stats['3_pts'],
            "basket_player_assists": 0,
            "basket_player_rebounds": 0,
            "basket_player_blocks": 0,
            "basket_player_steals": 0,
            "basket_player_fouls": g_stats['fautes'],
            "playing_time": convert_time(g_stats['tps_jeu'])
        }
        
    # 5. Send Player Update
    if payload_players:
        print("Mise à jour des stats joueurs...")
        resp_put_players = requests.put(url_players, headers=HEADERS, json=payload_players)
        if resp_put_players.status_code == 200:
            print("✅ Stats joueurs mises à jour !")
        else:
            print(f"❌ Erreur mise à jour joueurs: {resp_put_players.status_code}")
            print(resp_put_players.text)
            
    # 6. Update Opponents (Score)
    url_opponents = f"https://api.sporteasy.net/v2.1/teams/{team_id}/events/{event_id}/stats/opponents/"
    print(f"Récupération des stats match: {url_opponents}")
    resp_opponents = requests.get(url_opponents, headers=HEADERS)
    if resp_opponents.status_code != 200:
        print("Erreur récupération stats match")
        return
        
    opponents_data = resp_opponents.json()
    
    # Determine which team is left/right based on is_home
    # Usually opponent_left is home, but let's check the event data
    # In SportEasy, opponent_left is usually the home team.
    
    # From Gemini: equipe_A is Home, equipe_B is Away
    score_A = stats_data['match_info']['score_A_final']
    score_B = stats_data['match_info']['score_B_final']
    mitemps_A = stats_data['match_info'].get('score_A_mitemps', [0, 0])
    mitemps_B = stats_data['match_info'].get('score_B_mitemps', [0, 0])
    
    # Assuming opponent_left is ALWAYS Home (Equipe A) and opponent_right is Away (Equipe B)
    # If opponent_left['is_home'] is False, we might need to swap, but standard is Left=Home
    
    is_left_home = opponents_data['opponent_left']['is_home']
    
    if is_left_home:
        score_left = score_A
        score_right = score_B
        # Map halves to Q1 and Q2
        quarters_left = [mitemps_A[0], mitemps_A[1], 0, 0]
        quarters_right = [mitemps_B[0], mitemps_B[1], 0, 0]
    else:
        score_left = score_B
        score_right = score_A
        quarters_left = [mitemps_B[0], mitemps_B[1], 0, 0]
        quarters_right = [mitemps_A[0], mitemps_A[1], 0, 0]

    payload_opponents = {
        "left": {
            "score": str(score_left),
            "basket_period_one": str(quarters_left[0]),
            "basket_period_two": str(quarters_left[1]),
            "basket_period_three": str(quarters_left[2]),
            "basket_period_four": str(quarters_left[3]),
            "withdrawal": False
        },
        "right": {
            "score": str(score_right),
            "basket_period_one": str(quarters_right[0]),
            "basket_period_two": str(quarters_right[1]),
            "basket_period_three": str(quarters_right[2]),
            "basket_period_four": str(quarters_right[3]),
            "withdrawal": False
        }
    }
    
    print("Mise à jour du score...")
    resp_put_opponents = requests.put(url_opponents, headers=HEADERS, json=payload_opponents)
    if resp_put_opponents.status_code == 200:
        print("✅ Score mis à jour !")
    else:
        print(f"❌ Erreur mise à jour score: {resp_put_opponents.status_code}")
        print(resp_put_opponents.text)

def traitement_affichage_json(response, start_day=None, days_to_display=None):
        try:
            results = response.json()["results"]

            # Configuration des traductions
            JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

            # On laisse le premier vide pour que janvier soit à l'index 1
            MOIS = ["", "janvier", "février", "mars", "avril", "mai", "juin", 
                "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
            
            ancienne_date_construite = None
            i = 1

            result_trie = []

            for event in results:
                if event["type"]['id'] == 7 and event["team_name"] != "ARBITRES":

                    dt = datetime.fromisoformat(event["start_at"])

                    if start_day is not None:
                        if dt.day < start_day:
                            continue
                        if days_to_display is not None and dt.day >= start_day + days_to_display:
                            continue

                    date_construite = f"{JOURS[dt.weekday()]} {dt.day} {MOIS[dt.month]}"

                    if date_construite != ancienne_date_construite:
                        print(f"\n{date_construite} :")
                        ancienne_date_construite = date_construite

                    eq_a = event["opponent_left"]['full_name']
                    eq_b = event["opponent_right"]['full_name']
                    
                    print(f"{i} - {event['team_name']} : {eq_a} VS {eq_b} | {dt.strftime('%H:%M')}")
                    result_trie.append(event)
                    i += 1
            return result_trie, i-1
        except requests.exceptions.JSONDecodeError:
            print("❌ Erreur de lecture du JSON")
            print(response.text[:500])
            return None


def get_match(events, i):
    print(f"Numéro du match [1:{i}]")
    try:
        reponse = int(input("--> "))
    except ValueError:
        get_match(events, i)
        return

    if reponse > i or reponse < 1 :
        print(f"Erreur : Numéro du match doit être compris entre [1:{i}]")
        get_match(events, i)
        return

    match = events[reponse-1]
    print(match)
    
    print("\nQue voulez-vous faire ?")
    print("1. Voir les détails (déjà affiché)")
    print("2. Mettre à jour les stats via PDF")
    choix = input("--> ")
    
    if choix == "2":
        pdf_path = input("Chemin du fichier PDF : ").strip('"')
        update_event_stats(match, pdf_path)


def lancer(month, year, start_day=None, days_to_display=None):
    response_requete = requete_matchs_SE(f"https://api.sporteasy.net/v2.1/clubs/587/events/?month={month}&year={year}")

    matchs_trie, i = traitement_affichage_json(response_requete, start_day, days_to_display)

    get_match(matchs_trie, i)
lancer(12, 2025, 5, 3)
