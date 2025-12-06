import google.generativeai as genai
import os
import json

# Configuration (Assure-toi d'avoir ta clé API)
os.environ["GOOGLE_API_KEY"] = "AIzaSyBDQjWtTne9MDlPVE8Ky9-5g34wAGqTRBI"
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

# Initialisation du modèle
model = genai.GenerativeModel('gemini-2.5-flash')

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
        "score_A_mitemps": [MT1, MT2],
        "score_B_mitemps": [MT1, MT2]
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

# --- EXEMPLE D'UTILISATION ---

# Remplace par le chemin de ton fichier PDF ou Texte
fichier_match = "C:\\Users\\MrMenphis\\Downloads\\resume_0062_PRM_A_127_ALLOEU_BASKET_CLUB_BASKET_CLUB_VIOLAINES.pdf"

# Appel de la fonction
resultats = analyser_match_basket(fichier_match, "ALLOEU BASKET CLUB")


print(resultats)