# Spec 001 — Justificatifs Amazon automatiques dans QontoUpdate

Statut : **arbitrages A1→A5 tranchés le 09/11/2026**, A6 et feu vert en attente. Résumé de décision : `resume.html`, à côté.

## Constat

Chaque mois, des achats Amazon payés avec la carte Qonto restent sans
justificatif. QontoUpdate les signale en orange (« transaction sans
justificatif, à ajouter à la main »), et il faut aller chercher chaque
facture PDF sur amazon.fr puis la déposer dans Qonto.

Le 09/11/2026, ce travail a été fait une fois à la main pour adn dev :
15 transactions entre le 01/10 et le 09/11. Il a permis de valider la méthode :

- **API Qonto** : la clé `organisation:secret` déjà utilisée par l'application
  permet de lister les transactions et d'y **joindre un PDF**
  (`POST /v2/transactions/{id}/attachments`, réponse 200). La méthode
  `Qonto.addAttachment()` existe déjà.
- **Référence Qonto** : `406-5893060-4448314 AMZN Mktp FR 5SC0HUQNCTU0ODQ4`. Elle se lit
  ainsi : n° de commande, puis `AMZN Mktp FR` (Marketplace) ou `Amazon.fr`
  (Amazon vend directement), puis la **référence de paiement**.
- **Amazon** : `/your-orders/invoice/popover?orderId=<n°>` liste les factures
  d'une commande (`/documents/download/<uuid>/invoice.pdf`). Chaque PDF porte
  une ligne « Référence de paiement XXXX ». C'est la clé d'association : une
  commande peut avoir plusieurs factures et plusieurs débits.
- **Lecture du PDF** : PDFKit, intégré à macOS (via `osascript -l JavaScript`).
  Rien à installer.

Cas rencontrés sur les 15 transactions :

| Cas | Nombre | Exemple |
| --- | --- | --- |
| Référence trouvée, montant identique | 9 | 8,99 € ↔ facture 8,99 € |
| Référence trouvée, facture **partielle** | 4 | 74,03 € débités, facture de 8,99 € : les autres vendeurs du même débit n'ont pas encore émis leur facture |
| Référence trouvée, débit **inférieur** à la facture | 1 | 18,17 € débités par carte, le reste payé par chèque-cadeau |
| Commande sans aucune facture | 1 | seul le lien « Demander une facture » est proposé |

## Ce qu'on propose

Une étape **« Justificatifs Amazon »** ajoutée au traitement de chaque
société, **avant** la récupération des justificatifs (la fonction de base de
l'application). Elle s'insère dans `Qonto.addMissingAttachment()`, à côté des
sources Google et CDVI qui existent déjà.

### F1 — Repérer les transactions Amazon sans justificatif

- Le filtre ne compare jamais les libellés exactement. Qonto double les espaces
  (`AMAZON PAYMENTS EUROPE S  C  A`) et répète parfois l'émetteur
  (`… S C A AMAZON PAYMENTS EUROPE S C A`). On ramène d'abord les espaces
  à un seul et on met tout en majuscules, puis on reconnaît Amazon **soit
  par l'émetteur** (libellé ou contrepartie contenant `AMAZON`), **soit par la
  référence** (`AMZN`, ou n° de commande `XXX-XXXXXXX-XXXXXXX`).
- Formes relevées sur 12 mois (3 sociétés, 01/11/2025 → 09/11/2026), chacune
  avec son traitement :

  | Émetteur (libellé normalisé) | Référence | Vu | Traitement |
  | --- | --- | --- | --- |
  | `AMAZON PAYMENTS EUROPE S C A` | `<n° commande> AMZN Mktp FR <réf. paiement>` | 68 | F2 (Marketplace) |
  | `AMAZON EU SARL, SUCCURSALE FRANCAIS…` | `<n° commande> Amazon.fr <réf. paiement>` | 15 | F2 (vendu par Amazon) |
  | `AMAZON EU SARL, SUCCURSALE FRANCAIS…` | `D01-… Amazon Prime FR <réf. paiement>` | 1 | F2 si la facture est trouvée, sinon F3 (abonnement / commande numérique) |
  | `AMAZON PAYMENTS` | *(vide)* | 7 | F3 directement : pas de n° de commande, donc rien pour faire le lien (lien vers « Vos commandes ») |
  | `AMAZON PAYMENTS EUROPE S C A`, **crédit** | `<n° commande> AMZN Mktp FR <réf.>` | 1 | Remboursement : voir A5 |

  La référence est analysée avec
  `^([A-Z0-9]{3}-\d{7}-\d{7}) (AMZN Mktp FR|Amazon\.fr|Amazon Prime FR) (\S+)$`.
  Une transaction Amazon que ce motif ne reconnaît pas n'est **jamais ignorée** :
  elle passe en F3 avec son libellé brut, pour qu'une forme nouvelle se voie
  tout de suite.
- Le contrôle porte sur toutes les transactions sans justificatif, et
  **pas seulement sur le mois traité** :
  - **dans la période** (mois de la génération en cours) → elles passent par F2 ;
  - **hors période** → elles sont seulement signalées (date, montant, lien), sans
    rien bloquer. Voir l'arbitrage A1.
- Une transaction qui a déjà un justificatif n'est jamais touchée.

### F2 — Retrouver et joindre la facture

Pour chaque transaction de la période :

1. ouvrir les factures de la commande sur amazon.fr ;
2. télécharger chaque PDF, lire sa « Référence de paiement » ;
3. retenir la facture dont la référence est égale à la fin de la référence Qonto ;
4. si le **total de la facture est égal au montant débité** → joindre par l'API,
   sans rien demander ;
5. sinon → F3.

Une même transaction n'est jamais justifiée deux fois. Si l'application est
relancée, la transaction a déjà un justificatif et F1 l'ignore.

### F3 — Demander à l'utilisateur en cas de problème

Quand une transaction ne peut pas être justifiée automatiquement, l'application
**s'arrête et pose la question dans l'interface**. Elle ne choisit jamais à la place
de l'utilisateur. Chaque transaction en problème affiche :

- la **date** et le **montant** débité, la société ;
- la **cause**, en clair (facture partielle : facturé X € sur Y € débités ;
  aucune facture ; référence introuvable) ;
- un lien **« Voir la commande sur Amazon »**
  (`https://www.amazon.fr/gp/your-account/order-details?orderID=<n°>`) ;
- pour une commande sans facture, un lien **« Demander une facture »**.

Choix proposés, selon le cas :

| Cas | Choix |
| --- | --- |
| Facture partielle ou montant différent | Joindre la facture trouvée · Laisser sans justificatif |
| Aucune facture / référence introuvable | Laisser sans justificatif · Réessayer (après avoir obtenu la facture) |

Une transaction « laissée sans justificatif » reste orange dans le
récapitulatif, avec son lien Amazon, comme aujourd'hui.

### F4 — Session Amazon

- Le navigateur est **Google Chrome, déjà installé**, piloté par Playwright pour
  Python (`channel="chrome"`), avec un **profil dédié** rangé dans le dossier
  de l'application. Pas de Chromium à télécharger. Le profil ne touche pas à
  ton Chrome habituel.
- À la première utilisation, ou quand Amazon redemande une connexion, la fenêtre
  s'affiche et l'interface indique « Connecte-toi à Amazon dans la fenêtre
  ouverte ». L'application attend, puis reprend seule.
- Aucun mot de passe n'est stocké par l'application. Seul le profil du
  navigateur garde la session.

### F5 — Interface

- Une ligne « Amazon » par société dans le récapitulatif : nombre de factures
  jointes, partielles, manquantes.
- Une carte **« Décision Amazon »** apparaît au-dessus des logs quand F3 a
  besoin d'une réponse. Le mode automatique actuel (qui répond « Entrée » à
  toutes les questions) **ne répond jamais** à cette carte.
- Le bouton « Valider » reste désactivé tant qu'une transaction n'a pas de
  choix. Si on clique quand même, la carte indique laquelle manque.

Technique : le script émet une ligne `QONTO_DECISION {json}` (sur le modèle de
`status.STATUS_PREFIX`), puis attend la réponse sur stdin. Le lanceur Flask
l'expose dans `/api/logs` et la réponse revient par `/api/answer`.

### F6 — Choisir le mois à générer

Aujourd'hui, l'interface lance toujours le script en mode automatique, qui
répond « Entrée » à `Will run on date … ? (Y/n)` : c'est toujours le **mois
précédent** qui est généré, sans possibilité d'en choisir un autre depuis
l'interface.

- Dans la carte « Contrôles », un menu **« Mois à générer »** propose les 12
  derniers mois. Par défaut : le mois précédent, comme aujourd'hui.
- Le mois choisi est passé au script (`--month AAAA_MM`). La question
  `Y/n` n'est alors plus posée. Sans `--month`, le comportement en ligne de
  commande ne change pas.
- Ce mois définit la **période** utilisée par F1 : les transactions Amazon d'un
  autre mois sont signalées « hors période ».
- **Mois en cours** : visible dans le menu avec la mention « en cours », mais
  « Démarrer » est refusé avec la raison : le relevé Qonto du mois n'est
  publié qu'au début du mois suivant, donc le zip serait rouge (voir A6).
- Le titre de la carte de décision et le récapitulatif rappellent le mois
  choisi.

## Ce qu'on ne fait pas

- Pas d'autre site marchand qu'amazon.fr. Les sources Google et CDVI ne bougent pas.
- Pas de demande de facture envoyée au vendeur à ta place.
- Pas de rapprochement article par article des factures partielles :
  l'interface donne le lien vers la commande, c'est toi qui regardes.
- Pas de stockage des factures en dehors du zip mensuel actuel.

## Risques

- **Amazon change ses pages** : l'URL `invoice/popover` ou le texte
  « Référence de paiement » peuvent changer. L'application doit alors **échouer en
  rouge** avec la cause (« aucune facture lisible pour la commande X »), pas
  joindre au hasard.
- **Captcha / double authentification Amazon** : le cas est prévu par F4
  (la fenêtre s'affiche, on attend).
- **Nouvelle dépendance** : `playwright` dans `qontoenv` (installation pip).
  Chrome doit être installé sur le Mac.
- **Facture partielle jointe** : la transaction ne remonte plus comme « sans
  justificatif », alors que la justification n'est que partielle. C'est
  pourquoi F3 demande toujours.

## Arbitrages

Tranchés le 09/11/2026 :

- **A1** — Transactions Amazon sans justificatif hors période : **les signaler seulement**.
- **A2** — Écart dû à un chèque-cadeau : **demander quand même**.
- **A3** — Questions **regroupées par société**.
- **A4** — Sans réponse : **attendre sans limite**.
- **A5** — Remboursements : **chercher l'avoir et le joindre**, avec la même règle
  que les factures (référence de paiement, puis montant ; sinon décision).

En attente :

- **A6** — Mois en cours : **refuser la génération** (proposé) ou l'autoriser
  en ne faisant que l'étape Amazon, sans zip ni relevé ?

## Tests (chaque élément de spec testé)

- F1 : les 5 formes du tableau, avec espaces doublés et émetteur répété ;
  une forme inconnue mais « AMAZON » part en décision, n'est jamais ignorée ;
  tri dans la période / hors période ; transaction déjà justifiée ignorée.
- F2 : association par référence de paiement sur plusieurs factures et plusieurs
  débits d'une même commande (cas réel 406-8138195-3514724) ; montant égal →
  ajout ; montant différent → décision ; jamais deux ajouts.
- F3 : contenu de la décision (date, montant, cause, liens) ; chaque choix
  produit le bon effet ; le mode auto ne répond pas.
- F4 : session expirée → attente puis reprise (navigateur simulé).
- F5 : « Valider » refuse une réponse incomplète.
- F6 : `--month` respecté et question `Y/n` sautée ; défaut = mois précédent ;
  mois en cours refusé ; la période de F1 suit le mois choisi.

Les appels Amazon et Qonto sont simulés dans les tests ; aucun test ne joint de
fichier sur le vrai compte.
