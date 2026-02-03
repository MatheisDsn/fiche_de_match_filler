import streamlit as st
import requests
from datetime import datetime, timedelta
import google.generativeai as genai
from google.api_core import exceptions
import os
import json
import difflib
import tempfile
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
st.set_page_config(page_title="SportEasy Stats Updater", page_icon="🏀")

# Récupération de la clé API depuis les secrets Streamlit
api_key = None
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
    os.environ["GOOGLE_API_KEY"] = api_key
    genai.configure(api_key=api_key)
    # Utilisation de gemini-1.5-flash qui est plus rapide et a souvent de meilleurs quotas gratuits
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    st.error("⚠️ Clé API Google Gemini manquante dans st.secrets")

# Configuration Google Sheets
gsheet_client = None
if "gcp_service_account" in st.secrets:
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scopes
        )
        gsheet_client = gspread.authorize(credentials)
    except Exception as e:
        st.sidebar.error(f"⚠️ Erreur connexion Google Sheets: {e}")

# --- HEADERS & COOKIES ---
# Initialiser le cookie sporteasy dans session_state s'il n'existe pas
if 'sporteasy_cookie_value' not in st.session_state:
    st.session_state['sporteasy_cookie_value'] = "gl53blz0iqxbxhjho0vzz2wzzluf1eir"

# Champ pour saisir uniquement la valeur du cookie sporteasy
sporteasy_value = st.sidebar.text_input(
    "Cookie SportEasy",
    value=st.session_state['sporteasy_cookie_value'],
    help="Entrez uniquement la valeur du cookie sporteasy (ex: gl53blz0iqxbxhjho0vzz2wzzluf1eir)"
)

# Sauvegarder la valeur actuelle dans session_state
st.session_state['sporteasy_cookie_value'] = sporteasy_value

# Construire la chaîne complète des cookies
user_cookies = (
    "se_csrftoken=67meREjj8e05BzDVEN2Nrq32w45hrPZk; "
    "se_referer=\"https://www.google.com/\"; "
    "se_first_url=https%3A%2F%2Fwww.sporteasy.net%2Ffr%2F; "
    "se_last_url=\"/fr/profile/teams/\"; "
    "didomi_token=eyJ1c2VyX2lkIjoiMTliMTcwMDYtYTEyZC02OTU4LWIyMWUtMTQ3ZDRkZWQ0ZTFkIiwiY3JlYXRlZCI6IjIwMjUtMTItMTNUMDk6MTc6NDEuNzc4WiIsInVwZGF0ZWQiOiIyMDI1LTEyLTEzVDA5OjE3OjU5LjE1NloiLCJ2ZXJzaW9uIjoyLCJ2ZW5kb3JzIjp7ImVuYWJsZWQiOlsiZ29vZ2xlIiwiYzpnb29nbGVhbmEtNFRYbkppZ1IiLCJjOmxpbmtlZGluLW1hcmtldGluZy1zb2x1dGlvbnMiLCJjOmh1YnNwb3QiLCJjOmFtcGxpdHVkZSIsImM6eW91dHViZSIsImM6aG90amFyIiwiYzpuZXctcmVsaWMiLCJjOmh1YnNwb3QtZm9ybXMiLCJjOmxpbmtlZGluIl19LCJ2ZW5kb3JzX2xpIjp7ImVuYWJsZWQiOlsiZ29vZ2xlIl19LCJhYyI6IkFGbUFDQUZrLkFGbUFDQUZrIn0=; "
    f"sporteasy={sporteasy_value}; "
    "euconsent-v2=CQcXr0AQcXr0AAHABBENCIFgAP_AAELAAAqIGSQAgF5gMkAySAEAvMBkgAAA.f_gACFgAAAAA; "
    "_ga=GA1.1.392473986.1765617478; "
    "_ga_N6SPHF8K4P=GS2.1.s1765617477$o1$g1$t1765617725$j42$l0$h856859297"
)

# Extraire le CSRF token des cookies
def extract_csrf_token(cookie_string):
    """Extrait le token CSRF depuis la chaîne de cookies"""
    import re
    match = re.search(r'se_csrftoken=([^;]+)', cookie_string)
    if match:
        return match.group(1).strip()
    return None

csrf_token = extract_csrf_token(user_cookies)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
    "Accept": "application/json",
    "Referer": "https://alloeu-basket-club.sporteasy.net/",
    "Origin": "https://alloeu-basket-club.sporteasy.net",
    "x-csrftoken": csrf_token if csrf_token else "",
    "Cookie": user_cookies
}

# Afficher un avertissement si le CSRF token est manquant
if not csrf_token:
    st.sidebar.warning("⚠️ CSRF token manquant ! Les modifications (PUT) échoueront. Ajoutez 'se_csrftoken=...' au début des cookies.")

# --- FONCTIONS UTILITAIRES ---

def get_forum_url(event_id, team_slug):
    """Construit l'URL du forum du match"""
    return f"https://{team_slug}.sporteasy.net/event/{event_id}/forum/"

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

def update_google_sheet(noms_officiels):
    """Met à jour le Google Sheet avec les officiels de table"""
    if not gsheet_client:
        st.warning("⚠️ Connexion Google Sheets non configurée")
        return
    
    if not noms_officiels:
        st.info("ℹ️ Aucun officiel de table détecté")
        return
    
    try:
        sheet_id = st.secrets.get("GOOGLE_SHEET_ID")
        sheet_name = st.secrets.get("GOOGLE_SHEET_NAME", "Feuille 1")
        
        if not sheet_id:
            st.error("❌ GOOGLE_SHEET_ID manquant dans secrets.toml")
            return
        
        # Ouvrir le Google Sheet
        spreadsheet = gsheet_client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        # Récupérer toutes les données (colonne A = noms, colonne B = compteurs)
        all_data = worksheet.get_all_values()
        
        # Créer un dictionnaire des noms existants {nom: ligne}
        existing_data = {}
        if len(all_data) > 1:  # Si plus que l'en-tête
            for idx, row in enumerate(all_data[1:], start=2):  # Start à 2 car ligne 1 = header
                if len(row) >= 2 and row[0]:  # Si nom existe
                    existing_data[row[0].strip().lower()] = {
                        'row': idx,
                        'count': int(row[1]) if row[1].isdigit() else 0
                    }
        
        # Mettre à jour ou ajouter chaque officiel
        updates = []
        for nom in noms_officiels:
            nom_clean = nom.strip()
            nom_lower = nom_clean.lower()
            
            if nom_lower in existing_data:
                # Incrémenter
                row_num = existing_data[nom_lower]['row']
                new_count = existing_data[nom_lower]['count'] + 1
                worksheet.update_cell(row_num, 2, new_count)
                updates.append(f"✅ {nom_clean}: {existing_data[nom_lower]['count']} → {new_count}")
            else:
                # Ajouter nouvelle ligne
                next_row = len(all_data) + 1
                worksheet.update_cell(next_row, 1, nom_clean)
                worksheet.update_cell(next_row, 2, 1)
                updates.append(f"✨ {nom_clean}: Nouveau (1)")
        
        if updates:
            st.success(f"📊 Google Sheet mis à jour ({len(updates)} officiels)")
            for update in updates:
                st.write(update)
    
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("❌ Google Sheet introuvable. Vérifie l'ID et partage le sheet avec le service account.")
    except Exception as e:
        st.error(f"❌ Erreur mise à jour Google Sheet: {e}")

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
            # st.write(f"✅ Match: {g_player['joueur']} -> {best_match['profile']['full_name']}")
        else:
            st.warning(f"⚠️ Pas de correspondance pour: {g_player['joueur']}")
            
    return mapping

def analyser_feuille_match(chemin_fichier):
    """Analyse la feuille de match officielle pour extraire les officiels de table (page 2)"""
    prompt = """
    Tu es un assistant expert en statistiques de basket. Analyse ce document qui contient la feuille de match officielle.
    
    IMPORTANT : Focus UNIQUEMENT sur la PAGE 2 du document.
    
    Tâche : Extraction des officiels de table
    - En bas de la page 2, cherche l'encadré contenant les officiels de table
    - Extrais TOUS les noms pour ces rôles (certaines cases peuvent être vides) :
      - Marqueur
      - Chronométreur
      - Chronométreur des tirs (ou "Chrono Tirs" ou "24 secondes" ou "Opérateur 24 sec")
      - Aide Marqueur
    - Si un rôle est vide, ne l'inclus pas dans la liste
    - Extrais UNIQUEMENT les noms (Nom Prénom), pas les rôles

    Format de réponse attendu :
    Réponds UNIQUEMENT avec un objet JSON valide (sans Markdown ```json) suivant cette structure :
    {{
      "officiels_table": [
        "Nom Prénom",
        "Autre Nom"
      ]
    }}
    """
    
    mon_fichier = genai.upload_file(chemin_fichier, mime_type="application/pdf")
    
    with st.spinner("📋 Analyse de la feuille de match (officiels de table)..."):
        try:
            response = model.generate_content([mon_fichier, prompt])
        except exceptions.ResourceExhausted:
            st.error("⚠️ Quota Gemini dépassé (ResourceExhausted). Le modèle gratuit a atteint ses limites. Attendez quelques minutes ou utilisez une autre clé API.")
            return None
        except Exception as e:
            st.error(f"Une erreur s'est produite lors de l'appel à Gemini : {e}")
            return None
    
    try:
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_text)
        return data
    except json.JSONDecodeError:
        st.error("Erreur : La réponse de Gemini n'est pas un JSON valide.")
        st.code(response.text)
        return None

def analyser_match_basket(chemin_fichier, nom_club_cible="ALLOEU BASKET CLUB"):
    """Analyse le résumé de match pour extraire les scores et statistiques des joueurs"""
    prompt = f"""
    Tu es un assistant expert en statistiques de basket. Analyse ce document qui contient le résumé de match.
    
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

    mon_fichier = genai.upload_file(chemin_fichier, mime_type="application/pdf")
    
    with st.spinner(f"📊 Analyse du résumé de match pour {nom_club_cible}..."):
        try:
            response = model.generate_content([mon_fichier, prompt])
        except exceptions.ResourceExhausted:
            st.error("⚠️ Quota Gemini dépassé (ResourceExhausted). Le modèle gratuit a atteint ses limites. Attendez quelques minutes ou utilisez une autre clé API.")
            return None
        except Exception as e:
            st.error(f"Une erreur s'est produite lors de l'appel à Gemini : {e}")
            return None
    
    try:
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_text)
        return data
    except json.JSONDecodeError:
        st.error("Erreur : La réponse de Gemini n'est pas un JSON valide.")
        st.code(response.text)
        return None

def update_event_stats(event, resume_path, feuille_path):
    club_name = "ALLOEU BASKET CLUB" 
    
    # Analyse du résumé de match (scores + stats joueurs)
    stats_data = analyser_match_basket(resume_path, club_name)
    if not stats_data:
        return

    st.success("✅ Analyse du résumé de match terminée !")
    st.json(stats_data['match_info'])
    
    # Analyse de la feuille de match (officiels de table)
    officiels_data = analyser_feuille_match(feuille_path)
    if officiels_data and 'officiels_table' in officiels_data and officiels_data['officiels_table']:
        st.divider()
        st.subheader("📋 Officiels de table détectés")
        for officiel in officiels_data['officiels_table']:
            st.write(f"• {officiel}")
        update_google_sheet(officiels_data['officiels_table'])
    else:
        st.warning("⚠️ Aucun officiel de table détecté dans la feuille de match")

    team_id = event['opponent_right']['id'] if event['opponent_right']['is_current_team'] else event['opponent_left']['id']
    event_id = event['id']
    
    # --- JOUEURS ---
    url_players = f"https://api.sporteasy.net/v2.1/teams/{team_id}/events/{event_id}/stats/players/"
    resp_players = requests.get(url_players, headers=HEADERS)
    
    if resp_players.status_code == 200:
        se_players = resp_players.json()['players']
        player_mapping = match_players(stats_data['stats_club_cible'], se_players)
        
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
            
        if payload_players:
            resp_put_players = requests.put(url_players, headers=HEADERS, json=payload_players)
            if resp_put_players.status_code == 200:
                st.success(f"✅ Stats de {len(payload_players)} joueurs mises à jour !")
            else:
                st.error(f"❌ Erreur mise à jour joueurs: {resp_put_players.status_code}")
    else:
        st.error("Impossible de récupérer la liste des joueurs SportEasy")

    # --- SCORE ---
    url_opponents = f"https://api.sporteasy.net/v2.1/teams/{team_id}/events/{event_id}/stats/opponents/"
    resp_opponents = requests.get(url_opponents, headers=HEADERS)
    
    if resp_opponents.status_code == 200:
        opponents_data = resp_opponents.json()
        
        score_A = stats_data['match_info']['score_A_final']
        score_B = stats_data['match_info']['score_B_final']
        mitemps_A = stats_data['match_info'].get('score_A_mitemps', [0, 0])
        mitemps_B = stats_data['match_info'].get('score_B_mitemps', [0, 0])
        
        is_left_home = opponents_data['opponent_left']['is_home']
        
        if is_left_home:
            score_left = score_A
            score_right = score_B
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
        
        resp_put_opponents = requests.put(url_opponents, headers=HEADERS, json=payload_opponents)
        if resp_put_opponents.status_code == 200:
            st.success("✅ Score et quarts-temps mis à jour !")
        else:
            st.error(f"❌ Erreur mise à jour score: {resp_put_opponents.status_code}")

# --- INTERFACE UTILISATEUR ---

st.title("🏀 Gestion Matchs SportEasy")

# Initialiser session_state si nécessaire
if 'matchs' not in st.session_state:
    st.session_state['matchs'] = []

# Obtenir le mois et l'année actuels
current_date = datetime.now()
current_month = current_date.month
current_year = current_date.year

# Checkbox pour le filtre des 5 jours
filter_5_days = st.checkbox("Afficher uniquement les matchs de moins de 5 jours", value=True)

# Afficher les sélecteurs de mois/année uniquement si le filtre n'est pas actif
if not filter_5_days:
    col1, col2 = st.columns(2)
    with col1:
        month = st.number_input("Mois", min_value=1, max_value=12, value=current_month)
    with col2:
        year = st.number_input("Année", min_value=2024, max_value=2030, value=current_year)
else:
    # Valeurs par défaut si le filtre est actif
    month = current_month
    year = current_year

if st.button("Charger les matchs"):
    url = f"https://api.sporteasy.net/v2.1/clubs/587/events/?month={month}&year={year}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        results = response.json()["results"]
        matchs = []
        now = datetime.now()
        five_days_ago = now - timedelta(days=5)
        
        for event in results:
            if event["type"]['id'] == 7 and event["team_name"] != "ARBITRES" or event["type"]['id'] == 5 or event["type"]['id'] == 4 :
                dt = datetime.fromisoformat(event["start_at"])
                # Retire le fuseau horaire pour la comparaison
                dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
                
                # Appliquer le filtre des 5 jours seulement si la checkbox est cochée
                if filter_5_days:
                    if dt_naive >= five_days_ago:
                        label = f"{dt.strftime('%d/%m')} - {event['team_name']} : {event['opponent_left']['full_name']} VS {event['opponent_right']['full_name']}"
                        matchs.append({"label": label, "data": event})
                else:
                    label = f"{dt.strftime('%d/%m')} - {event['team_name']} : {event['opponent_left']['full_name']} VS {event['opponent_right']['full_name']}"
                    matchs.append({"label": label, "data": event})
        
        st.session_state['matchs'] = matchs
        
        if filter_5_days:
            st.success(f"{len(matchs)} matchs trouvés (moins de 5 jours).")
        else:
            st.success(f"{len(matchs)} matchs trouvés pour {month}/{year}.")
    else:
        st.error(f"Erreur chargement matchs: {response.status_code}")

if 'matchs' in st.session_state and st.session_state['matchs']:
    selected_match_label = st.selectbox("Sélectionner un match", [m['label'] for m in st.session_state['matchs']])
    selected_match = next(m['data'] for m in st.session_state['matchs'] if m['label'] == selected_match_label)
    
    st.write("---")
    st.subheader("Mise à jour via PDF")
    
    st.info("📄 Il faut fournir 2 documents PDF distincts :")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**1️⃣ Résumé de match**")
        st.caption("Contient les scores et statistiques des joueurs")
        resume_file = st.file_uploader("📊 Résumé de match (PDF)", type="pdf", key="resume")
    
    with col2:
        st.markdown("**2️⃣ Feuille de match officielle**")
        st.caption("Contient les officiels de table (page 2)")
        feuille_file = st.file_uploader("📋 Feuille de match (PDF)", type="pdf", key="feuille")
    
    if resume_file is not None and feuille_file is not None and api_key:
        if st.button("🚀 Lancer l'analyse et la mise à jour"):
            # Sauvegarde temporaire des fichiers pour Gemini
            with tempfile.NamedTemporaryFile(delete=False, suffix="_resume.pdf") as tmp_resume:
                tmp_resume.write(resume_file.getvalue())
                resume_path = tmp_resume.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix="_feuille.pdf") as tmp_feuille:
                tmp_feuille.write(feuille_file.getvalue())
                feuille_path = tmp_feuille.name
            
            try:
                update_event_stats(selected_match, resume_path, feuille_path)
                # Affiche le bouton forum après succès
                st.divider()
                st.subheader("Accéder au forum")
                
                # Récupère le slug de l'équipe (exemple: 'alloeu-basket-club-u11')
                team_slug = selected_match.get('team_slug', 'alloeu-basket-club-u11')
                event_id = selected_match['id']
                forum_url = get_forum_url(event_id, team_slug)
                
                st.markdown(f"### [🔗 Accéder au forum du match]({forum_url})", unsafe_allow_html=True)
                st.info(f"Forum: {forum_url}")
            finally:
                # Nettoyage des fichiers temporaires
                os.remove(resume_path)
                os.remove(feuille_path)
