import streamlit as st
import requests
from datetime import datetime, timedelta
import google.generativeai as genai
from google.api_core import exceptions
import os
import json
import difflib
import tempfile

# --- CONFIGURATION ---
st.set_page_config(page_title="SportEasy Stats Updater", page_icon="🏀")

# Récupération de la clé API depuis les secrets Streamlit ou input utilisateur
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    api_key = st.sidebar.text_input("Clé API Google Gemini", type="password")

if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
    genai.configure(api_key=api_key)
    # Utilisation de gemini-1.5-flash qui est plus rapide et a souvent de meilleurs quotas gratuits
    model = genai.GenerativeModel('gemini-2.5-flash')

# --- HEADERS & COOKIES ---
# Idéalement, mettez ces cookies dans st.secrets aussi pour ne pas les exposer
DEFAULT_COOKIES = (
    "se_referer=\"https://www.google.com/\"; "
    "se_first_url=https%3A%2F%2Fwww.sporteasy.net%2Ffr%2F; "
    "se_last_url=\"/fr/profile/teams/\"; "
    "didomi_token=eyJ1c2VyX2lkIjoiMTliMTcwMDYtYTEyZC02OTU4LWIyMWUtMTQ3ZDRkZWQ0ZTFkIiwiY3JlYXRlZCI6IjIwMjUtMTItMTNUMDk6MTc6NDEuNzc4WiIsInVwZGF0ZWQiOiIyMDI1LTEyLTEzVDA5OjE3OjU5LjE1NloiLCJ2ZXJzaW9uIjoyLCJ2ZW5kb3JzIjp7ImVuYWJsZWQiOlsiZ29vZ2xlIiwiYzpnb29nbGVhbmEtNFRYbkppZ1IiLCJjOmxpbmtlZGluLW1hcmtldGluZy1zb2x1dGlvbnMiLCJjOmh1YnNwb3QiLCJjOmFtcGxpdHVkZSIsImM6eW91dHViZSIsImM6aG90amFyIiwiYzpuZXctcmVsaWMiLCJjOmh1YnNwb3QtZm9ybXMiLCJjOmxpbmtlZGluIl19LCJ2ZW5kb3JzX2xpIjp7ImVuYWJsZWQiOlsiZ29vZ2xlIl19LCJhYyI6IkFGbUFDQUZrLkFGbUFDQUZrIn0=; "
    "sporteasy=a4lgdp0ogd6elkscw9wxguhmd86fekdt; "
    "euconsent-v2=CQcXr0AQcXr0AAHABBENCIFgAP_AAELAAAqIGSQAgF5gMkAySAEAvMBkgAAA.f_gACFgAAAAA; "
    "_ga=GA1.1.392473986.1765617478; "
    "_ga_N6SPHF8K4P=GS2.1.s1765617477$o1$g1$t1765617725$j42$l0$h856859297"
)

user_cookies = st.sidebar.text_area("Cookies SportEasy (si changés)", value=DEFAULT_COOKIES, height=100)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
    "Accept": "application/json",
    "Referer": "https://alloeu-basket-club.sporteasy.net/",
    "Origin": "https://alloeu-basket-club.sporteasy.net",
    "x-csrftoken": "WzwU5QNlQTysEJNOww2NACxltnk4mXs5",
    "Cookie": user_cookies
}

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

def analyser_match_basket(chemin_fichier, nom_club_cible="ALLOEU BASKET CLUB"):
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

    mon_fichier = genai.upload_file(chemin_fichier, mime_type="application/pdf")
    
    with st.spinner(f"Analyse du match pour {nom_club_cible} en cours avec Gemini..."):
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

def update_event_stats(event, pdf_path):
    club_name = "ALLOEU BASKET CLUB" 
    
    stats_data = analyser_match_basket(pdf_path, club_name)
    if not stats_data:
        return

    st.success("Analyse PDF terminée !")
    st.json(stats_data['match_info'])

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

col1, col2 = st.columns(2)
with col1:
    month = st.number_input("Mois", min_value=1, max_value=12, value=12)
with col2:
    year = st.number_input("Année", min_value=2024, max_value=2030, value=2025)

if st.button("Charger les matchs"):
    url = f"https://api.sporteasy.net/v2.1/clubs/587/events/?month={month}&year={year}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        results = response.json()["results"]
        matchs = []
        
        for event in results:
            if event["type"]['id'] == 7 or event["team_name"] != "ARBITRES" or event["type"]['id'] == 5 :
                dt = datetime.fromisoformat(event["start_at"])
                label = f"{dt.strftime('%d/%m')} - {event['team_name']} : {event['opponent_left']['full_name']} VS {event['opponent_right']['full_name']}"
                matchs.append({"label": label, "data": event})
        
        st.session_state['matchs'] = matchs
        st.success(f"{len(matchs)} matchs trouvés.")
    else:
        st.error(f"Erreur chargement matchs: {response.status_code}")

if 'matchs' in st.session_state and st.session_state['matchs']:
    selected_match_label = st.selectbox("Sélectionner un match", [m['label'] for m in st.session_state['matchs']])
    selected_match = next(m['data'] for m in st.session_state['matchs'] if m['label'] == selected_match_label)
    
    st.write("---")
    st.subheader("Mise à jour via PDF")
    
    uploaded_file = st.file_uploader("Choisir la feuille de match (PDF)", type="pdf")
    
    if uploaded_file is not None and api_key:
        if st.button("Lancer l'analyse et la mise à jour"):
            # Sauvegarde temporaire du fichier pour Gemini
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
            
            try:
                update_event_stats(selected_match, tmp_path)
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
                os.remove(tmp_path) # Nettoyage
