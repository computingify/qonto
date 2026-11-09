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
  Pastilles de statut par société
----------------------------------------
Gris    : en attente
Bleu    : traitement en cours
Vert    : terminé sans problème
Orange  : terminé, mais un point à vérifier
          (zip non copié car déjà présent, transaction sans
           justificatif à ajouter à la main sur Qonto…)
Rouge   : échec — le zip est incomplet ou n'a pas été produit
          (relevé Qonto non récupéré, API injoignable, clé
           invalide, relevé Bourse Direct absent, copie impossible…)

Dès qu'une société est orange ou rouge, un encadré « Problèmes
détectés » apparaît sous les pastilles et donne la cause exacte,
avec le nom de fichier attendu quand il s'agit d'un relevé.

----------------------------------------
  Relevés de compte
----------------------------------------
Les relevés Qonto sont téléchargés automatiquement via l'API
(endpoint /v2/statements) : plus rien à faire à la main, ni mail,
ni navigateur, ni dépôt dans ~/Downloads.

Si l'API est injoignable ou si le relevé du mois n'est pas encore
publié par Qonto, la société passe en ROUGE et le zip n'est pas
produit. Il n'y a volontairement aucun repli sur ~/Downloads : le
relevé vient de l'API ou ne vient pas.

Seule exception : le relevé Bourse Direct d'ADN Group, qui n'est
pas exposé par Qonto. Il reste à télécharger à la main dans
~/Downloads (pdf_*.pdf).

----------------------------------------
  Mois à générer
----------------------------------------
Menu « Mois à générer » dans Contrôles : par défaut le mois précédent.
Le mois en cours est refusé (le relevé Qonto n'est publié qu'au début
du mois suivant). En Terminal : --month AAAA_MM.

----------------------------------------
  Justificatifs Amazon (spec 001)
----------------------------------------
Avant la récupération des justificatifs, l'app cherche les transactions
Amazon sans justificatif du mois choisi, télécharge les factures sur
amazon.fr (Google Chrome, profil dédié dans amazon-profile/) et joint
celle dont la « Référence de paiement » et le montant correspondent.
Facture partielle, absente ou illisible : une carte « Décision Amazon »
s'affiche et l'app attend la réponse. Les transactions d'autres mois
sont seulement signalées.
Première fois (ou session expirée) : une fenêtre Chrome s'ouvre sur la
connexion Amazon, se connecter dedans, l'app reprend seule.

----------------------------------------
  Lancement manuel (équivalent, Terminal)
----------------------------------------
python3 gui_launcher.py

Installer les dépendances :
pip3 install -r ./install.txt

Ancienne version :
python3 run.py
