from datetime import datetime

# Ta variable
date_str = "2025-12-05T20:45:00+01:00"

# 1. Convertir la chaîne en objet datetime
date_obj = datetime.fromisoformat(date_str)

# 2. Récupérer le nom du jour (en anglais par défaut)
jour_anglais = date_obj.strftime("%A")

print(jour_anglais) 
# Résultat : Friday