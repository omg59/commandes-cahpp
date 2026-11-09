# Historique des versions

## Horizon 2.0.0b5 — première préversion publiée, 9 novembre 2026

- publication des paquets Windows et Linux validés, avec sources identifiées et empreintes SHA-256 ;
- compilation avec Python 3.15 et dépendances compatibles ;
- nouveau logo, colonne fournisseur dédiée et améliorations du parcours de commande.

Voir les [notes de version](docs/releases/2.0.0b5.md).

## Construction Horizon — téléchargements AppImage, 8 novembre 2026

- nouvelles tentatives sur erreurs réseau temporaires et accès officiel de secours ;
- cache des outils entre les builds, avec contrôle SHA-256 systématique ;
- journaux indiquant précisément le fichier et la tentative en échec.

## Branche Horizon — nettoyage du dépôt, 8 novembre 2026

- retrait de l’ancienne interface Tkinter, de ses lanceurs, installateurs et tests graphiques ;
- conservation du moteur métier, des migrations 1.6 et de leurs tests ;
- documentation et contrôles de compilation recentrés sur Horizon.

## Horizon 2.0.0b3 — saisie de quantité, 8 novembre 2026

- fenêtre « Quantité à ajouter » élargie pour garder son titre lisible ;
- saisie d’un nombre entier de cartons, à partir de 1, sans décimales.

## Horizon 2.0.0b2 — identité indépendante et ajout au panier, 8 novembre 2026

- retrait du logo institutionnel, de ses fichiers et de ses références dans
  l'interface, les notices, la documentation et la capture du README ;
- demande du nombre de cartons avant l'ajout d'un article, quantité habituelle
  préremplie et cumul sur une ligne existante ; annuler conserve le panier ;
- sélecteur fournisseur des statistiques élargi et redimensionnable.

## Horizon 2.0.0b1 — première bêta utilisateur, 7 novembre 2026

- suppression du titre redondant dans Paramètres → Fournisseurs ;
- premier lancement avec création d'une base vide, import d'une base 1.6 ou
  ouverture d'un profil existant ; choix du profil mémorisé après redémarrage ;
- sélecteur de profil accessible depuis les paramètres, anciens profils conservés ;
- retrait du chargement des données d'exemple et des mentions alpha/profil d'essai ;
- nouvelle capture réelle de l'interface bêta dans le README Horizon ;
- vérification des bases vides, des imports et de la réouverture du profil mémorisé
  depuis les véritables paquets Linux et Windows.

## Horizon 2.0.0a9 — navigation et identité visuelle, 7 novembre 2026

- logo Horizon et titres centrés dans la barre latérale ; ancien logo en bas ;
- un seul bouton Commandes avec les onglets Nouvelle commande, Suivi des commandes
  et À recommander ; conservation du panier et accès directs adaptés ;
- Paramètres → À propos : auteur Damien Macq, version, crédits, informations
  sur les données et consultation des notices/licences jointes ;
- vérification des ressources graphiques et des notices dans les paquets compilés.

## Horizon 2.0.0a8 — dates des exports, 7 novembre 2026

- rétablir AAAA-MM-JJ pour les noms des PDF et des exports Excel ;
- afficher les dates Excel en AAAA-MM-JJ tout en conservant de vraies dates ;
- conserver JJ/MM/AAAA dans les écrans et champs de saisie du logiciel.

## Horizon 2.0.0a7 — dates françaises, 7 novembre 2026

- dates affichées et saisies en JJ/MM/AAAA dans les commandes, le suivi,
  les réceptions, les documents, les notes, les imports et les paramètres ;
- tri chronologique conservé, heures en format 24 h et erreurs de saisie françaises ;
- dates françaises dans les exports Excel et les noms des nouveaux PDF ;
- « Envoyer l'e-mail au fournisseur », puis « Envoyer à nouveau l'e-mail au fournisseur »
  après ouverture, y compris à la reprise d'un message déjà préparé ;
- formats de stockage et de synchronisation inchangés.

## Horizon 2.0.0a6 — libellés de la fenêtre d’envoi, 7 novembre 2026

- « Bon de commande » remplace « Bon PDF » ;
- boutons « Ouvrir l’e-mail » et « Ouvrir le dossier des pièces jointes » ;
- libellés conservés après l’ouverture de la messagerie.

## Horizon 2.0.0a5 — envoi simplifié, 7 novembre 2026

- après validation et création du PDF, fenêtre d'envoi sans quitter la commande ;
- accès direct au message prérempli, au PDF et au dossier des pièces jointes ;
- confirmation explicite de l'envoi dans la même fenêtre, avec reprise ultérieure ;
- bouton d'envoi direct dans l'historique, sans menu d'actions intermédiaire ;
- gestion des fournisseurs déplacée dans Paramètres → Fournisseurs ;
- tests du parcours complet, des annulations, des erreurs et des pièces jointes.

## Horizon 2.0.0a4 — paquets Linux, 7 novembre 2026

- construction Linux x86_64 : AppImage autonome et archive portable tar.gz ;
- lanceur AppRun, entrée de bureau et icône de l'application intégrés ;
- outils AppImage et runtime figés, vérifiés par empreinte SHA-256 ;
- construction CI sous Ubuntu 22.04 pour limiter la version minimale de glibc ;
- lancement et reprise de base testés depuis les vrais paquets, sans FUSE ;
- ouverture d'une copie dans une instance AppImage indépendante du montage initial ;
- artefacts Linux, manifeste de construction et empreintes accessibles dans Actions.

## Horizon 2.0.0a3 — retours d'utilisation, 7 novembre 2026

- logo de l'application et icônes Windows repris exactement de la 1.6.0 ;
- libellés « Nouvelle commande » et « Ma commande » ;
- panneau de commande élargi et colonnes référence/désignation séparées,
  sans rappel du fournisseur dans les articles de la commande ;
- recherche saisissable des fournisseurs par tout ou partie de leur nom,
  sans réutilisation implicite d'un ancien choix pendant la saisie ;
- diagnostic et copie de base regroupés dans les paramètres ;
- interrupteur soleil/lune accessible au clavier, mode clair/sombre mémorisé ;
- vérification de la reprise des réglages d'établissement, fournisseurs,
  modèles et favoris, et documentation de la migration depuis la 1.6.0.

## Horizon 2.0.0a2 — fonctions de la 1.6.0, 7 novembre 2026

- paramètres établissement, PDF, e-mails, collaboration et maintenance ;
- fiches fournisseurs complètes, favoris avancés, notes/remplacements et articles locaux ;
- dates de commande, contrôles minimum/franco/cartons et commandes similaires ;
- filtres d'historique mémorisés, archives, duplication complète/sélective et e-mails ;
- confirmations, échéances, réceptions partielles en unités, reliquats et facturation ;
- documents typés, pièces jointes d'e-mail, notes internes et audit des actions ;
- recommandations, statistiques détaillées, dates libres et export Excel ;
- collaboration persistante, verrous, numérotation et catalogues partagés ;
- diagnostic Qt complet, copie/export du rapport, journaux et reconstruction FTS en arrière-plan ;
- copie autonome des documents et du logo lors de la reprise d'une base ;
- installateur Horizon distinct et détection de ses mises à jour sur le partage ;
- tests métier à deux postes et parcours graphique complet incluant le débogage.

La branche reste `feature/horizon-ui` ; version moteur et schéma inchangés.

## Horizon 2.0.0a1 — branche parallèle, 7 novembre 2026

- première interface Qt/PySide6 : accueil, catalogue, préparation, historique et
  statistiques avec courbe mensuelle et barres par fournisseur ;
- adaptation visuelle aux supports graphiques fournis, logo conservé sans retouche,
  thèmes clair/sombre et dialogues standard en français ;
- profils de démonstration et copies isolées de la base, y compris journal WAL,
  sans ouverture de la base stable comme base de travail ;
- réutilisation de la recherche FTS5, des imports transactionnels, des garde-fous
  de commande et du générateur PDF de la 1.6.0 ;
- tableaux paginés, recherches annulables en arrière-plan et fermeture coordonnée
  des workers Qt ; calculs du panier en Decimal ;
- compilation Windows distincte et artefact portable produit par la CI Horizon ;
- collaboration, réceptions détaillées, messagerie, pièces jointes et réglages
  complets à porter. Alpha réservée aux essais : voir [le guide](docs/horizon.md).

## 1.6.0 — 7 novembre 2026

- prise en charge du nouveau fichier CAHPP **Evo TARIFS** : détection des en-têtes
  anciens et nouveaux, tolérance aux variantes d'accents, espaces et casse,
  lecture en flux et prise en charge de colonnes supplémentaires ;
- compatibilité avec les catalogues complets historiques dont la colonne
  réservée `ARTICLEACTIF` est vide ; statut explicite toujours exigé dans les
  fichiers mensuels et les instantanés partagés ;
- distinction explicite entre catalogue complet et évolutions mensuelles :
  les articles absents d'un fichier mensuel restent conservés et actifs ;
  les retraits et réactivations suivent `ARTICLEACTIF` ;
- aperçu avant import, contrôle d'une base complète initiale, de l'ordre des
  mois et des révisions, refus des doublons, données invalides et fichiers
  modifiés en cours de lecture ; réimport identique sans doublon ;
- sauvegarde complète automatique avant chaque nouvel import depuis l'interface,
  transaction unique et retour à l'état précédent en cas d'échec, y compris
  pendant la reconstruction de l'index ;
- conservation des quantités connues lorsque le fichier ne fournit plus
  `Conditionnement` et `Qml`, sans déduction à partir des désignations ;
- filtre **Articles à vérifier uniquement**, contrôle des nouvelles références,
  conditionnements modifiés, TVA manquantes et types d'évolution
  inconnus ; confirmation explicite avant commande, liée à l'évolution courante ;
- protection des brouillons dont le conditionnement a changé ; conservation des
  commandes historiques, notes, favoris et corrections manuelles ; conservation
  des coordonnées et de l'identité historique lors d'un changement de nom fournisseur ;
- partage d'un catalogue complet reconstitué après chaque évolution : un nouveau
  poste ou un poste resté hors ligne peut rattraper directement le dernier état ;
  archivage du fichier mensuel source avec vérification d'intégrité ;
- contrôle des publications concurrentes et reprise après coupure sans réappliquer
  l'import ; synchronisation des confirmations de vérification entre postes ;
- import séparé en modules de format, application transactionnelle et export
  partagé, avec tests de régression et parcours Tk complet ;
- diagnostic enrichi avec le mois courant et les articles à vérifier ;
- migration additive vers le schéma SQLite 15 et intégration des correctifs de
  recherche de la 1.5.2. Tous les postes doivent passer en 1.6.0 avant le partage
  des nouveaux catalogues ;
- compilation et essai utilisateur sous Windows 11 confirmés : nouvelles
  références, variations de prix, remplacements et arrêts de commercialisation ;
  diagnostic sans anomalie, index intègre et mois de novembre appliqué.

## 1.5.2 — correctifs intégrés à la 1.6.0

- correction d'un parcours SQL coûteux sur les grands catalogues : consultation
  des correspondances FTS5 avant la lecture des fiches produits ;
- actualisation ciblée des statistiques du planificateur au premier contrôle
  ou à la première recherche, puis après import ou reconstruction ; prévention
  des parcours complets dus à des statistiques issues d'un ancien petit catalogue ;
- contrôle en arrière-plan, sans analyse répétée à chaque frappe ; attente
  d'écriture limitée pour cette actualisation et nouvelle tentative différée
  en cas d'indisponibilité, sans déclarer l'index corrompu ;
- diagnostic enrichi avec l'état des statistiques et le plan d'une recherche
  témoin, sans conserver la recherche saisie ;
- conservation de la limite de temps, des filtres, de la priorité des favoris,
  des corrections d'articles et de la pagination ;
- tests de régression sur un grand catalogue avec statistiques périmées,
  y compris recherche sans résultat et budget de travail SQLite ;
- scénario de lenteur reproduit avec SQLite 3.49.1 sur 158 488 articles fictifs ;
- conservation du schéma SQLite 14 ; compilation et essai Windows nécessaires
  avant diffusion. La correction sur le poste concerné reste à confirmer.

## 1.5.1

- ajout de **Reconstruire l'index** dans **Paramètres → Collaboration → Diagnostic**,
  avec exécution en arrière-plan et protection contre les lancements multiples ;
- recréation de la table FTS5 et de ses entrées à partir du catalogue local,
  puis contrôle d'intégrité et test d'une recherche avec classement avant validation ;
- reconstruction transactionnelle : retour à l'index précédent en cas d'échec,
  sans modification des commandes, fournisseurs, articles ni réglages ;
- contrôle automatique renforcé : détection des textes périmés et des structures
  FTS5 défectueuses même lorsque les nombres d'articles et d'entrées correspondent ;
- délai de 30 secondes entre deux reconstructions automatiques échouées,
  sans empêcher une nouvelle tentative manuelle ;
- rapport de diagnostic enrichi avec le test fonctionnel, le dernier résultat
  de reconstruction de la session, sa durée et une catégorie d'erreur technique ;
- messages de recherche distinguant un index indisponible d'un dépassement de délai ;
- tests de corruption avec comptes identiques, de schéma incorrect, de rollback,
  de transaction d'import et du bouton Tk en arrière-plan ;
- conservation du schéma SQLite 14 ; compilation et installation Windows
  à valider sur un poste de test avant diffusion.

## 1.5.0

- reprise depuis l'historique des commandes générées ou avec e-mail préparé,
  tant qu'elles ne sont ni envoyées ni suivies ; conservation du numéro,
  des lignes, de la date, des pièces jointes et du journal ;
- invalidation de la référence au PDF et de la préparation d'e-mail lors de
  la reprise, avec avertissement sur les copies exportées et brouillons externes ;
- contrôle transactionnel interdisant la modification directe d'une commande
  envoyée ou générée ; vérification du verrou collaboratif avant enregistrement ;
- recherche de produits en arrière-plan dans **Nouvelle commande**,
  annulation dès la frappe et affichage par lots de 25, avec pages de 100 ;
- annulation immédiate des recherches obsolètes également dans **Catalogue** ;
- protection des saisies de commande contre les rafraîchissements automatiques
  et confirmation avant de quitter avec des modifications non enregistrées ;
- retours des workers de synchronisation, de diagnostic et de maintenance
  transmis par une file consommée par le thread graphique ; renouvellement
  périodique des verrous déplacé en arrière-plan ;
- découpage de l'ancien `ui.py` en modules par écran et composants communs,
  en conservant l'import public `cahpp_app.ui.App` ;
- conversion numérique commune avec virgules et espaces français, refus des
  valeurs non finies et validation des quantités, prix et taux de TVA ;
- affichage des nombres avec arrondi décimal `ROUND_HALF_UP` ; le stockage
  SQLite des montants reste inchangé ;
- tests de reprise, de synchronisation, de validation et d'annulation ;
  scénario graphique fournisseur/article/commande avec fermeture et réouverture ;
- script `build_release.bat` : cohérence des versions, lint, tests, compilation
  et manifeste de l'installateur avec empreinte SHA-256 ;
- conservation du schéma SQLite 14 ; validation Windows et installation
  manuelle encore requises avant publication.

## 1.4.3

- documentation regroupée dans `docs/` : guide collaboratif, validation commune
  et développement/publication ; retrait des checklists et notices par version
  devenues redondantes avec le changelog et les guides courants ;
- correction du `KeyError` lors de la fermeture des suggestions fournisseur
  quand le focus appartient à une fenêtre Tcl native (liste de combobox) ;
- test graphique reproduisant un focus Tcl inconnu du registre Python ;
- fermeture déterministe des connexions SQLite après chaque bloc de lecture
  ou de transaction, y compris lors de l'initialisation ;
- conservation de la validation et de l'annulation des transactions en cas
  d'erreur ; libération garantie des connexions de sauvegarde ;
- correction des erreurs Windows `WinError 32` lors du nettoyage des bases
  temporaires encore ouvertes ;
- correction du test de dossier PDF lorsque Windows utilise un chemin court
  (`RUNNER~1`) pour le même dossier physique ;
- quatre tests de non-régression de fermeture, commit et rollback, sans
  dépendre du ramasse-miettes Python ;
- aucun changement de schéma de base de données.

## 1.4.2

- journal local rotatif (4 fichiers de 1 Mio maximum) pour le démarrage,
  la recherche, les erreurs d'interface, de workers, de PDF et de synchronisation ;
- journalisation des types d'erreurs, codes système et piles techniques sans
  enregistrer les recherches saisies, les données de commande ni les messages
  bruts d'exception ;
- rapport de diagnostic enrichi avec les événements récents, l'architecture
  du processus et les versions SQLite et Tk ;
- nettoyage des fichiers temporaires après échec d'une écriture JSON atomique ;
- retrait des verrous perdus de la liste des verrous utilisables ;
- tests de panne de publication, reprise, JSON endommagé et perte de verrou ;
- tests du journal, de sa rotation et du fonctionnement sans droit d'écriture ;
- test graphique isolé : construction et visite des neuf pages et recherche ;
- workflow GitHub Actions Windows/Linux : tests, Ruff, compilation Python et
  vérification PyInstaller sur Windows ;
- conservation du schéma SQLite 14.

## 1.4.1

- suppression autorisée dans l'historique pour les commandes **Brouillon**,
  **Générée** et **E-mail préparé**, tant qu'elles n'ont pas été marquées envoyées ;
- protection conservée si un envoi, une confirmation, une réception ou une
  facturation est enregistré, même si le statut affiché est incohérent ;
- confirmation explicite avant suppression et journal de suppression conservé ;
- propagation de la suppression aux autres postes par le mécanisme collaboratif ;
- nettoyage des pièces jointes locales et du dossier de préparation d'e-mail ;
- conservation des PDF exportés séparément ; rappel de retirer manuellement
  tout brouillon déjà ouvert dans la messagerie ;
- vérification atomique de l'éligibilité avant suppression ;
- tests de suppression après génération/préparation d'e-mail, synchronisation
  et refus de suppression des commandes envoyées ou suivies.

## 1.4.0

- recherche du catalogue déplacée hors du thread graphique afin d'éviter les
  gels de l'interface sur les postes plus lents ;
- worker unique conservant seulement la saisie la plus récente et annulant les
  recherches devenues obsolètes ;
- vérification automatique de la cohérence entre les articles et l'index FTS5 ;
- reconstruction automatique d'un index incomplet, absent ou endommagé ;
- suppression du basculement silencieux vers une recherche intégrale coûteuse ;
- mode de secours limité dans le temps lorsque FTS5 reste indisponible ;
- délai de saisie porté à 400 ms et recherche automatique à partir de deux
  caractères ;
- affichage progressif par lots de 25 lignes, avec 100 résultats initiaux et
  bouton **Afficher 100 de plus** ;
- enrichissement du rapport de diagnostic avec le nombre d'articles indexés,
  les entrées manquantes et les entrées orphelines ;
- ajout de tests de régression sur l'auto-réparation et les frappes rapides.

## 1.3.3

- correction de la conversion des points en virgules dans les coordonnées des
  fournisseurs ;
- format français limité aux seuls champs numériques **Minimum HT** et
  **Franco HT** ;
- réparation automatique et prudente des adresses e-mail, sites web, numéros
  de téléphone et coordonnées de contact déjà touchés par le défaut ;
- normalisation également appliquée aux données fournisseurs reçues par la
  synchronisation collaborative ;
- conservation des points dans les références, désignations, détails de
  conditionnement et notes lors de la modification d'un article ;
- migration automatique du schéma SQLite de la version 13 à 14.

## 1.3.2

- remplacement du séparateur classique du tableau de bord par le composant
  `ttk` compatible avec l'environnement Windows de compilation ;
- correction du blocage au démarrage provoqué par une option graphique non
  reconnue dans la première archive 1.3.1 ;
- conservation des tableaux redimensionnables et de leurs ascenseurs.

## 1.3.1

- ouverture maximisée par défaut afin d'utiliser l'espace réellement
  disponible sur l'écran ;
- séparation redimensionnable entre les tableaux des livraisons et des
  alertes ;
- ajout d'un ascenseur vertical indépendant sur chacun de ces tableaux ;
- conservation de l'état de sauvegarde et des boutons d'action en bas de la
  vue d'ensemble.

## 1.3.0

- alertes configurables lorsqu'une commande reste sans confirmation ou dépasse
  son échéance de livraison ;
- affichage des alertes sur le tableau de bord avec accès direct à la commande ;
- page **À recommander** calculant les échéances à partir des intervalles réels ;
- recommandation sélective de certains articles d'une ancienne commande ;
- détection d'une commande probablement créée en double dans les sept jours ;
- filtres personnalisés enregistrables dans l'historique ;
- délais moyens de confirmation et de livraison par fournisseur ;
- comparaison du dernier prix commandé avec le prix actuel du catalogue ;
- export Excel multi-feuilles des statistiques ;
- notes internes et référence de remplacement configurables sur un article ;
- ajout d'un service ou d'une unité destinataire sur la commande et son PDF ;
- lancement direct d'un installateur trouvé dans le dossier partagé, puis
  fermeture propre de l'application ;
- migration automatique du schéma SQLite de la version 12 à 13.

## 1.2.0

- ajout du statut **Confirmée** et d'une date de livraison prévisionnelle ;
- ajout des statuts **Partiellement livrée**, **Livrée** et **Facturée** ;
- saisie de plusieurs réceptions pour une même commande, avec date, numéro de
  bon de livraison, utilisateur et note ;
- réception article par article avec contrôle des quantités et calcul immédiat
  des reliquats ;
- correction ou suppression d'une réception avec recalcul automatique ;
- ajout de notes internes horodatées et partagées entre les utilisateurs ;
- synchronisation des réceptions, reliquats, confirmations, factures et notes ;
- enrichissement du tableau de bord avec l'état et le nombre d'unités restant à
  recevoir ;
- migration automatique du schéma SQLite de la version 11 à 12.

## 1.1.0

- ajout d'un tableau de bord des commandes envoyées restant à livrer ;
- ajout des états de livraison **En attente** et **Livrée**, synchronisés entre
  les postes et consignés dans le journal de la commande ;
- ajout d'une page **Statistiques** avec sélection de période et analyses par
  fournisseur et produit ;
- ajout de l'archivage automatique configurable des commandes livrées ;
- maintien des archives dans la base et possibilité de les afficher dans
  l'historique ;
- ajout d'un rappel visuel de sauvegarde et de la date du dernier contrôle ;
- contrôle périodique de l'intégrité SQLite et entretien hebdomadaire léger ;
- détection des nouveaux installateurs placés dans le sous-dossier partagé
  `mises-a-jour` ;
- migration automatique et compatible du schéma SQLite de la version 10 à 11.

## 1.0.1

- correction de l'icône du raccourci Bureau lors d'une mise à jour ;
- utilisation explicite de `assets\\app_icon.ico` par les raccourcis du
  Bureau et du menu Démarrer ;
- recréation du raccourci Bureau existant pendant l'installation, même si la
  tâche optionnelle n'est plus cochée lors d'une mise à jour ;
- respect du choix des utilisateurs qui n'ont aucun raccourci Bureau.

## 1.0.0

- publication de la première version stable après validation de la RC5 ;
- ajout de l'icône officielle **colis + checklist**, assortie aux couleurs de
  l'application ;
- création d'un fichier ICO multirésolution pour Windows, de 16 à 256 pixels ;
- affichage de l'icône dans la barre de titre et les fenêtres de
  l'application ;
- intégration de l'icône à l'exécutable PyInstaller, aux raccourcis, à
  l'installeur et au programme de désinstallation ;
- conservation intégrale des fonctions et correctifs validés en RC5 ;
- passage de la version affichée et des métadonnées d'installation à 1.0.0.

## 1.0.0-rc5

- retour à une barre d'actions unique dans l'historique des commandes ;
- augmentation de la largeur initiale de l'application à 1 450 pixels et
  largeur minimale fixée à 1 420 pixels afin de conserver tous les boutons
  entièrement visibles ;
- centrage de la fenêtre de classement d'un document sur la fenêtre
  **Documents associés** ;
- maintien du centrage dans les limites de l'écran ;
- conservation de l'autocomplétion sans perte de focus et des autres
  corrections introduites en RC4c.

## 1.0.0-rc4c

- remplacement du menu déroulant natif ouvert pendant la recherche d'un
  fournisseur par une liste de suggestions intégrée qui ne prend pas le focus
  clavier ;
- saisie continue de plusieurs lettres sans devoir recliquer dans le champ ;
- navigation possible dans les suggestions avec les flèches, la touche Entrée
  ou la souris ;
- réorganisation des actions de l'historique sur deux lignes afin d'éviter les
  boutons tronqués avec la mise à l'échelle de Windows ;
- remplacement de **Regénérer le PDF** par
  **Régénérer la commande** ;
- remplacement de **Documents / bon de livraison** par
  **Documents associés** ;
- suppression du raccourci redondant **Ajouter un bon de livraison** dans la
  fenêtre des documents ; le type reste disponible avec
  **Ajouter un document…**.

## 1.0.0-rc4b

- remplacement du libellé **Générer le PDF** par
  **Générer la commande** ;
- ajustement automatique des largeurs de colonnes une fois la largeur réelle
  de la page connue ;
- nouvel ajustement lors du redimensionnement de la fenêtre, sans masquer les
  colonnes situées à droite ;
- application de ce comportement au catalogue, aux articles disponibles et au
  contenu de la nouvelle commande ;
- ouverture automatique de la liste des fournisseurs filtrés pendant la
  saisie, sans devoir cliquer sur la flèche du champ ;
- détection d'Inno Setup lorsqu'il est installé uniquement pour l'utilisateur
  dans `AppData\Local`, via WinGet, Scoop ou son entrée de registre.

## 1.0.0-rc4

- ajout de catégories explicites pour les documents liés : bon de livraison,
  confirmation de commande, facture, devis, avoir, correspondance et pièce
  jointe e-mail ;
- ajout d'un type personnalisé pour classer les autres documents ;
- modification après ajout du type d'un document et de son inclusion dans la
  préparation du mail, désormais deux propriétés indépendantes ;
- élargissement du sélecteur aux principaux formats bureautiques, images,
  messages enregistrés et archives ;
- tri ascendant ou descendant par clic sur les en-têtes du catalogue, de la
  liste d'articles disponibles et du contenu de la commande ;
- maintien du tri choisi après une recherche ou un rafraîchissement ;
- ajout d'un script créant un installeur Windows unique sans droit
  administrateur ;
- lors d'une mise à jour par l'installeur, remplacement limité à l'exécutable
  et à ses dépendances, sans effacer la base locale, les documents, le logo,
  les PDF ni les sauvegardes.

## 1.0.0-rc3

- ajout d'un délai de synchronisation automatique configurable de 15 secondes
  à 10 minutes, avec une minute par défaut ;
- ajout de l'option, activée par défaut, mettant la synchronisation automatique
  en pause lorsqu'une fiche contient des modifications non enregistrées ;
- détection des saisies en cours dans les paramètres de l'établissement et
  dans les fiches fournisseurs ;
- protection contre le rafraîchissement d'un formulaire modifié, y compris
  lorsqu'une synchronisation avait déjà commencé avant la saisie ;
- reprise et synchronisation immédiate après l'enregistrement ;
- avertissement avant d'abandonner une fiche fournisseur non enregistrée ;
- précision accrue des horodatages collaboratifs afin qu'une sauvegarde faite
  juste après une réception soit toujours considérée comme la plus récente ;
- suppression de toute mention du franco atteint ou non atteint dans le PDF ;
- conservation du contrôle du franco uniquement dans l'interface, avant
  l'enregistrement ou la génération de la commande.

## 1.0.0-rc2

- ajout de **Supprimer le brouillon** dans l'historique ;
- limitation stricte de la suppression aux commandes encore au statut
  **Brouillon**, avec confirmation explicite ;
- utilisation du verrou collaboratif avant suppression pour empêcher
  l'effacement d'un brouillon ouvert sur un autre poste ;
- propagation de la suppression aux autres installations grâce à un marqueur
  versionné, empêchant le brouillon de réapparaître après synchronisation ;
- suppression des lignes, pièces jointes, copies d'envoi, fichiers partagés et
  anciennes révisions du brouillon ;
- conservation du numéro consommé afin de garantir la stabilité de la
  numérotation et de l'historique technique ;
- passage du schéma de base en version 10 avec migration automatique.

## 1.0.0-rc1

- ajout d'un diagnostic accessible depuis **Paramètres > Collaboration** ;
- contrôle SQLite `quick_check`, version du schéma, mode de journalisation,
  disponibilité de la recherche et détection d'enregistrements orphelins ;
- contrôle en lecture/écriture du dossier partagé, du renommage atomique, de
  l'identifiant de l'espace et de l'intégrité du catalogue publié ;
- affichage du nombre de commandes locales en attente et du bilan du dernier
  échange dans les paramètres et la barre latérale ;
- recensement des verrous actifs ou expirés et des utilisateurs concernés ;
- export ou copie d'un rapport de dépannage ne contenant ni tarif, ni ligne de
  commande, ni contenu de document ;
- ajout d'une checklist de validation à deux postes avant promotion en V1.0.

## 0.9.0

- ajout d'un mode collaboratif sans serveur : chaque poste conserve sa base
  SQLite locale et échange uniquement des fichiers versionnés dans un dossier
  réseau partagé ;
- création d'un profil nominatif au premier lancement, modifiable dans les
  paramètres, sans notion de poste ou d'emplacement ;
- choix, test, ouverture et modification du dossier partagé depuis l'onglet
  **Collaboration** ;
- synchronisation automatique et manuelle des commandes, fournisseurs,
  favoris, corrections du catalogue, articles hors catalogue et paramètres
  communs ;
- publication versionnée des catalogues CAHPP avec contrôle d'intégrité SHA-256
  et proposition d'installation sur les autres postes ;
- numérotation commune des commandes afin d'éviter les doublons ;
- verrou temporaire d'une commande ou d'un article pendant sa modification ;
- consultation locale maintenue lorsque le partage est indisponible, avec
  indication **Hors ligne — cache local** ;
- copie locale des PDF et documents reçus pour préserver leur consultation
  hors connexion ;
- ajout du créateur et de l'état de synchronisation dans l'historique ;
- ajout d'un journal nominatif des actions de chaque commande ;
- conservation de révisions récentes des données d'équipe et des commandes
  dans le dossier partagé ;
- retrait de la base de développement lors de la compilation du dossier
  portable : chaque poste démarre désormais avec sa propre base locale.

## 0.8.1b

- suppression de la fenêtre explicative après **Préparer le mail** ;
- conservation de l'ouverture automatique du message et du dossier contenant
  les pièces à joindre.

## 0.8.1

- retrait de la colonne redondante « Date du BC » dans l'historique ; la date
  reste conservée dans la base, le PDF et le nom du fichier ;
- suppression automatique du dossier temporaire
  `envois/<numero de commande>` lorsque la commande est marquée comme envoyée ;
- conservation du PDF original et des documents liés lors de ce nettoyage.

## 0.8.0

- ajout des dates de création et de premier envoi dans l'historique des
  commandes ;
- conservation de la première date d'envoi lorsqu'une commande est marquée
  plusieurs fois comme envoyée ;
- corrections locales des articles CAHPP sans modifier les valeurs importées,
  avec possibilité de rétablir les valeurs du catalogue ;
- modification et archivage des références créées par l'utilisateur ;
- suppression du code CAHPP dans le tableau du bon de commande PDF ;
- affichage automatique de la version du logiciel dans la barre latérale ;
- préparation des e-mails rendue plus générique, avec prise en charge de Gmail,
  des URL de composition génériques et des liens `mailto:` ;
- aide intégrée recensant les expressions utilisables dans l'objet et le corps
  des e-mails, dont `{date}` et `{total_ttc}`.

## 0.7.0

- remplacement des fenêtres de confirmation après enregistrement par un retour
  visuel temporaire directement sur le bouton concerné ;
- confirmation non bloquante pour les paramètres, les fournisseurs, les
  brouillons, la génération ou régénération des PDF et les sauvegardes ;
- affichage permanent de la section active dans la navigation latérale avec
  fond renforcé, texte en gras et liseré coloré ;
- conservation des fenêtres uniquement pour les erreurs, avertissements,
  décisions importantes et bilans détaillés.

## 0.6.1

- correction de la fenêtre des documents liés : la barre d'actions reste
  visible avec la mise à l'échelle de Windows et la hauteur s'adapte désormais
  au contenu et à l'écran.

## 0.6.0

- préparation locale des messages dans Gmail avec destinataire, objet et corps
  configurables ;
- regroupement automatique du PDF et des pièces jointes dans un dossier d'envoi ;
- duplication d'une ancienne commande en nouveau brouillon ;
- recherche dans l'historique par numéro, fournisseur, note, référence, code CAHPP
  ou désignation ;
- rattachement de bons de livraison et d'autres documents aux commandes ;
- intégration des documents liés dans la sauvegarde complète ZIP ;
- alerte après import pour les changements de prix ou de conditionnement
  concernant des articles déjà commandés ;
- coordonnées fournisseur enrichies, minimum de commande et franco ;
- contrôle des nombres de cartons non entiers et des seuils avant enregistrement ;
- affichage enrichi du conditionnement et favoris proposés par fournisseur ;
- migration automatique des bases créées avec les versions précédentes.

## 0.4.0

- nouveau nom PDF : `BC-AAAA-MM-JJ_Fournisseur.pdf` ;
- incrément journalier par fournisseur à partir de la deuxième commande.

## 0.3.0

- recherche par saisie dans la liste des fournisseurs ;
- création d'une commande directement depuis un article du catalogue ;
- choix du nom et de la destination lors de chaque génération PDF ;
- dossier PDF par défaut configurable.

## 0.2.0

- ajout de la modification des brouillons depuis l'historique ;
- conservation du numéro et de la date lors de la réédition ;
- titre du PDF personnalisable ;
- texte du pied de page personnalisable et vide par défaut ;
- affichage du numéro de page désactivable.

## 0.1.0

- import et mise à jour du catalogue CAHPP ;
- recherche, favoris, commandes et fournisseurs ;
- génération PDF et base SQLite portable.
