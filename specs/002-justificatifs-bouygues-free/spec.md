# Spec 002 — Justificatifs Bouygues Telecom et Free dans QontoUpdate

Statut : **arbitrages B1→B4 tranchés le 10/11/2026** (propositions retenues). Résumé de décision : `resume.html`, à côté.
Prolonge la spec 001 (Amazon) : mêmes règles de décision, même carte, même
mois choisi.

## Constat

Chaque mois, adn dev est prélevée par Bouygues Telecom (forfait mobile) et par
Free (Freebox). Les deux autres sociétés n'ont aucun prélèvement de ces
opérateurs (vérifié sur 12 mois, 01/11/2025 → 10/11/2026).

Ces factures sont **téléchargées et jointes à la main** : les PDF portent leur
nom d'origine et sont ajoutés de 2 jours à 5 semaines après le prélèvement.
Deux erreurs sont passées inaperçues :

| Débit | Justificatif joint | Attendu |
| --- | --- | --- |
| Bouygues 07/05/2026, 17,99 € | `Bouyguestelecom_Facture_20260527.pdf` (celle de juin) | facture du 27/04/2026, 17,99 € |
| Bouygues 09/04/2026, 18,07 € | `Bouyguestelecom_Facture_20260327.pdf` **deux fois** | une seule fois |

Les mails « Votre facture est disponible » ne contiennent **ni PDF ni lien
direct** vers le PDF : seulement un lien vers l'espace client
(`subscribe.free.fr/login/` ; pour Bouygues, `3fzy.adj.st/mes-factures` qui
redirige vers `bouyguestelecom.fr/mon-compte/mes-factures`). Il faut donc
passer par les espaces client, comme pour Amazon.

### Exploration du 10/11/2026 (session connectée, lecture seule)

**Free** (`adsl.free.fr`, ancien espace abonné en pages Perl)

- Après connexion, la page `home.pl?id=<abonné>&idt=<session>` liste
  **toutes les factures depuis 2019**, chacune sous la forme
  `facture_pdf.pl?id=…&idt=…&mois=AAAAMM&no_facture=<n°>`.
- Le PDF se récupère par un simple `GET` de ce lien, dans la session ouverte
  (`application/pdf`, nom proposé `Facture_Free_AAAAMM_<abonné>_<n°>.pdf`, le
  même que celui des PDF joints à la main).
- **Clé d'association exacte** : la référence Qonto `Free HautDebit 1510870586`
  contient le n° de facture, présent dans le lien. Vérifié sur novembre et
  octobre 2026.
- Le PDF porte « Total … 29,99€ » (TTC) et « Somme à payer le 04 Novembre 2026 ».

**Bouygues Telecom** (`bouyguestelecom.fr/mon-compte`, application JS sur
`api.bouyguestelecom.fr`)

- La page « Mes factures » appelle une requête GraphQL `GetInvoices`
  (`n: 10`, les 10 dernières factures). Chaque facture donne `id`,
  `mntTotFacture`, `dateFacturation` (le 27 du mois), `dateLimitePaieFacture`
  et le lien `facturePDF`.
- L'API exige un jeton dans l'en-tête `Authorization` : un `fetch` avec les
  seuls cookies est refusé (CORS). L'application **ne manipule pas ce jeton** :
  elle lit la réponse `GetInvoices` que la page reçoit, puis clique sur
  « Télécharger » dans la ligne de la facture et récupère le téléchargement
  (`Bouyguestelecom_Facture_AAAAMMJJ.pdf`, le même nom qu'aujourd'hui).
- **Pas de clé exacte côté Qonto** : la référence est le n° de ligne masqué
  (`06xxxxx055`). L'association se fait par le **montant** et la **date** :
  la facture du 27 du mois M-1 est prélevée vers le 7-9 du mois M. Sur les
  12 débits connus, le montant de la facture est toujours égal au débit.
- Le PDF porte en clair « Montant prélevé le 9 novembre 2026 17,99 », qui
  confirme l'association.

## Ce qu'on propose

Une étape **« Justificatifs opérateurs »** juste après l'étape Amazon, avant
la récupération des justificatifs. Le code d'Amazon est découpé pour que les
deux étapes partagent le repérage, la décision et le récapitulatif (voir B1).

### F1 — Repérer les transactions sans justificatif

- Libellé normalisé (espaces ramenés à un seul, majuscules), comme en 001.
- **Free** : libellé ou contrepartie contenant `FREE TELECOM` ; référence
  analysée par `^Free HautDebit (\d+)$`.
- **Bouygues** : libellé ou contrepartie contenant `BOUYGUES TELECOM`.
- Une transaction reconnue comme Free ou Bouygues dont la forme est inconnue
  (référence différente, crédit…) n'est **jamais ignorée** : elle part en
  décision avec son libellé brut.
- Même tri qu'en 001 : **dans la période** → F2 ; **hors période** →
  signalée seulement (A1 de la spec 001).

### F2 — Retrouver et joindre la facture

**Free**

1. ouvrir l'espace abonné, lire les liens `facture_pdf.pl` de la page
   d'accueil ;
2. retenir celui dont `no_facture` est égal au n° de la référence Qonto ;
3. télécharger le PDF, lire le total TTC ;
4. total égal au montant débité → joindre sans rien demander ; sinon → F3.

**Bouygues**

1. ouvrir « Mes factures », lire la réponse `GetInvoices` ;
2. retenir la facture **la plus récente émise avant le débit** dont le montant
   est égal au débit, émise au plus 45 jours avant ;
3. télécharger le PDF par le bouton de la ligne, vérifier la mention
   « Montant prélevé le <date> <montant> » ;
4. date et montant cohérents → joindre sans rien demander ; sinon → F3.

Une facture déjà jointe à une autre transaction n'est jamais proposée une
deuxième fois (c'est l'erreur de mai 2026).

### F3 — Décision

Même carte que la spec 001, avec l'opérateur en tête de chaque transaction.
Cas et choix :

| Cas | Choix |
| --- | --- |
| Facture trouvée, montant différent | Joindre la facture trouvée · Laisser sans justificatif |
| Aucune facture (pas encore émise, n° inconnu) | Laisser sans justificatif · Réessayer |
| Forme de transaction inconnue | Laisser sans justificatif · Réessayer |

Chaque transaction affiche la date, le montant, la cause en clair et un lien
vers l'espace client (« Voir mes factures Free » / « Voir mes factures
Bouygues »).

### F4 — Contrôle des justificatifs déjà joints (voir B3)

Pour les transactions Bouygues et Free **du mois traité** qui ont déjà un
justificatif, l'application compare le nom du fichier joint à la facture
attendue, quand le nom suit le format d'origine de l'opérateur :

- `Bouyguestelecom_Facture_AAAAMMJJ.pdf` : la date doit être celle de la
  facture attendue ;
- `Facture_Free_AAAAMM_<abonné>_<n°>.pdf` : le n° doit être celui de la
  référence Qonto ;
- un même fichier joint deux fois est signalé.

Un nom dans un autre format (`Mars_2026.pdf`) n'est pas vérifiable : il n'est
pas signalé. Ce contrôle **ne modifie rien** sur Qonto : il passe la société
en orange avec la cause exacte.

### F5 — Sessions

- Google Chrome installé, piloté par Playwright, comme Amazon. Profil réservé
  à l'application (voir B2 pour un profil commun ou un profil par site).
- Le navigateur n'est ouvert que s'il y a une transaction à traiter : un mois
  où tout est déjà justifié ne demande aucune connexion.
- Connexion demandée (page de login Free, `oauth2.bouyguestelecom.fr` ou
  code SMS) : la fenêtre s'affiche, l'interface indique « Connecte-toi à
  Free / Bouygues dans la fenêtre ouverte », l'application attend sans limite.
- Aucun mot de passe ni jeton stocké par l'application. Le jeton Bouygues
  n'est jamais lu : seule la page l'utilise.

### F6 — Interface

- La ligne « Amazon » du récapitulatif devient une ligne par source
  (Amazon, Bouygues, Free), affichée seulement si la source a eu quelque chose
  à traiter.
- La carte « Décision Amazon » devient « Décision justificatifs ». Une seule
  carte par société pour toutes les sources (comme A3 de la spec 001). Chaque
  transaction porte le nom de sa source.

## Ce qu'on ne fait pas

- **Pas de reverse-api-engineer** : l'outil génère un client d'API à partir du
  trafic capturé, mais ne gère ni la connexion ni la session, et son
  enregistrement (HAR) contient cookies et factures. L'exploration ci-dessus
  donne le même résultat sans dépendance.
- Pas de Free Mobile : aucun prélèvement sur les comptes Qonto des trois
  sociétés.
- Aucune suppression ni remplacement d'un justificatif déjà joint (F4 signale
  seulement). La correction de mai et avril 2026 reste à faire à la main.
- Pas de lecture des mails « facture disponible » : ils ne contiennent ni PDF
  ni lien utile.

## Risques

- **Free ou Bouygues change son espace client** : l'application échoue en
  rouge avec la cause (« liste des factures Free illisible »), ne joint jamais
  au hasard. L'espace Free en pages Perl date de plus de 15 ans, mais une
  refonte le ferait disparaître d'un coup.
- **Session courte** : la durée des sessions Free (`idt` dans l'URL) et
  Bouygues n'est pas connue. Il faudra peut-être se reconnecter tous les mois.
  Ce n'est gênant qu'une fois par mois, et seulement s'il y a une facture à
  chercher.
- **Bouygues ne rend que les 10 dernières factures** dans `GetInvoices`
  (`n: 10`). Générer un mois de plus de 10 mois en arrière ne trouvera pas la
  facture : décision « Aucune facture ».
- **Association Bouygues par montant** : deux factures de même montant à un
  mois d'écart. La règle « la plus récente avant le débit, pas déjà jointe »
  et la mention « Montant prélevé le … » du PDF lèvent l'ambiguïté.
- **Refactorisation d'Amazon** (B1) : le code de la spec 001 bouge. Les tests
  de la spec 001 doivent passer sans modification.

## Arbitrages

- **B1** — Socle commun : découper `amazon.py` maintenant (proposé) ou écrire
  `telecom.py` à côté sans toucher Amazon.
- **B2** — Profil Chrome : un profil commun `browser-profile/` pour les trois
  sites, l'actuel `amazon-profile/` étant renommé (proposé), ou un profil par
  site.
- **B3** — Justificatifs déjà joints : les contrôler et signaler (proposé),
  ou ne jamais les regarder comme en 001.
- **B4** — Montant Free différent (frais de retard, changement d'offre) :
  demander (proposé, même règle qu'Amazon) ou joindre quand même, le n° de
  facture étant une clé exacte.

## Tests (chaque élément de spec testé)

- F1 : libellés réels des deux opérateurs, espaces doublés ; forme inconnue
  envoyée en décision ; tri dans la période / hors période ; transaction
  justifiée ignorée par F2.
- F2 Free : n° trouvé et montant égal → ajout ; n° absent → décision ;
  montant différent → décision.
- F2 Bouygues : les 12 débits réels associés à la bonne facture (dont mai
  2026 → facture du 27/04) ; montant sans facture → décision ; facture déjà
  jointe jamais reproposée.
- F4 : mai 2026 signalé (mauvaise facture), avril 2026 signalé (doublon),
  `Mars_2026.pdf` non signalé, octobre 2026 conforme.
- F5 : aucun navigateur ouvert si rien à traiter.
- Non-régression : tous les tests de la spec 001 passent tels quels.
