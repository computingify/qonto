========================================
  QontoUpdate.app — Application Mac
========================================

USAGE NORMAL : double-cliquer sur QontoUpdate.app.
L'interface s'ouvre dans le navigateur (http://localhost:8000).
Pour arrêter : clic droit sur l'icône du Dock -> Quitter.

Astuce : glisser QontoUpdate.app dans le Dock pour le garder à portée.

--- RÉGLAGE UNIQUE (première utilisation) ---
macOS bloque l'accès aux dossiers Documents / Downloads pour les
applications lancées par double-clic. La première fois, l'app ouvre
automatiquement les Réglages Système au bon endroit :

  Réglages Système -> Confidentialité et sécurité
                   -> Accès complet au disque (Full Disk Access)

Ajouter / cocher « QontoUpdate », puis relancer l'app.
(Étape à faire une seule fois.)

Logs de l'app : ~/Library/Logs/QontoUpdate.log

----------------------------------------
  Lancement manuel (équivalent, Terminal)
----------------------------------------
python3 gui_launcher.py

Installer les dépendances :
pip3 install -r ./install.txt

Ancienne version :
python3 run.py
