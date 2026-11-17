# Consolidation après audit — développement

Lot coordonné : **Horizon PC 3.0.1a6**, **Horizon Server 0.5.0-dev4** et
**Horizon Mobile 0.6.0-dev4**. Les changements restent sur les branches `dev`.
Les versions principales et les releases publiées ne sont pas remplacées.

| Constat | Correction |
|---|---|
| H01 — réception invalide sans photo | Refus métier enregistré une fois ; la réception suivante est traitée. Les erreurs réseau et disque restent réessayables. |
| H02 — courses de réservation | Sentinelles permanentes, verrou natif de plage d’octets, vérification du propriétaire et publication dans une même section critique. Renouvellement indépendant des travaux réseau. |
| H03 — mélange de bases sur Android | Identité stable du partage et du relais, contrôle transactionnel côté serveur, stores Android isolés. Les anciennes données restent dans un espace distinct. |
| H04 — documents orphelins | Téléchargement autorisé seulement sur référence active, déduplication conservée, purge différée et bornée. Copies téléchargées Android séparées des fichiers à envoyer. |
| H05 — clé mobile commune | Clés par appareil, empreintes seules sur le relais, auteur lié à la clé, révocation et renouvellement indépendants. Fin de migration par désactivation de la clé commune. |
| H06 — croissance et réponses complètes | Historique incrémental avec suppressions, cache SQLite paginé, plafonds de files et de stockage, traitements par lots et rotation des caches. |
| H07 — clé PC en clair | Coffre natif, migration avec relecture, référence opaque dans le profil, repli en mémoire de session. |
| H08 — tests entre dépôts ignorables | CI privée obligatoire, sources PC/relais figées par SHA et rapport des versions exécutées ; une source manquante ou un test ignoré fait échouer le contrôle. |

## Données et mémoire

Le relais conserve la dernière modification de chaque commande avec une
séquence croissante, y compris une suppression explicite. Le téléphone avance
son curseur après chaque page enregistrée en transaction. Une coupure reprend
après la dernière page validée. Les modifications intervenues pendant une
fenêtre de lecture sont récupérées dans cette fenêtre ou au cycle suivant.

Android affiche 100 commandes par page ; recherche et filtres s’appliquent
**avant** la limitation. Les statistiques parcourent le cache complet des six
derniers mois, avec des montants décimaux, et signalent un chargement encore
incomplet. Le catalogue affiche une page de 40 références. Les anciens caches
JSON et les brouillons masqués sont transférés vers SQLite avant suppression
de leur copie dans les préférences.

Les plafonds Android sont de 100 demandes non archivées et 64 Mio de fichiers
de demandes par espace, 256 Mio/50 000 commandes dans son cache SQLite, et
100 Mio de copies documentaires téléchargées pour l’application. Un panier de
récupération est conservé dans un fichier atomique, séparé des petites
préférences. Les photos de réception et documents à envoyer ne sont jamais
effacés par le nettoyage du cache téléchargé.

Le relais traite au maximum 100 identifiants de demandes par file à chaque
lecture. Le PC publie au maximum 50 commandes par passage, avec un budget de
20 secondes entre commandes. Le catalogue continue de reprendre ses blocs
déjà confirmés. Un cycle Android récupère au maximum 20 pages ou 20 secondes
entre pages ; le chargement reprend automatiquement ensuite.

Les quotas serveur sont configurables, avec une réserve de disque. Un quota
atteint renvoie 429/507 ; l’erreur de stockage renvoie 503 et une trace technique
sans le contenu de l’exception. Les clients conservent les données à transmettre.
Les contenus de demandes terminées sont retirés du relais ; leurs empreintes et
résultats minimaux restent conservés sous quota pour préserver l’idempotence.

Le cache de catalogue du PC garde la génération courante et la précédente.
Les constructions abandonnées depuis plus d’un jour sont retirées. Un verrou
local empêche la rotation pendant la lecture des blocs d’un transfert actif.

## Déploiement de test

1. Sauvegarder les profils PC, le partage et le volume du relais. Utiliser une
   copie de test pour la première validation du lot.
2. Fermer tous les anciens PC, installer la même nouvelle version sur chacun
   et effectuer la [migration du protocole de partage](verrouillage-partage.md).
   Vérifier son exclusion sur le vrai lecteur réseau, dans les deux sens, avec
   les boutons de test à deux postes.
3. Mettre à jour le relais en conservant son volume ; puis rattacher la bonne
   base depuis le PC, avec confirmation si des données historiques existent.
4. Enregistrer les téléphones, connecter leurs clés individuelles et terminer
   la migration en désactivant la clé commune. Voir [les accès mobiles](acces-mobiles.md).
5. Installer Android avec la signature habituelle et vérifier sur les deux
   téléphones : ancienne base isolée, panier, brouillon, création, réception
   avec/sans photo, document, fonctionnement hors connexion et reprise.

Le relais reste une projection et une file d’échange ; le PC reste le moteur
métier. Aucun serveur supplémentaire n’est imposé à la collaboration PC.

Un retour en arrière exige l’arrêt coordonné des clients et la restauration des
profils, du partage et du volume sauvegardés. Ne pas remettre seulement l’ancien
manifeste pendant que des clients du nouveau protocole sont ouverts.

## Construction et suivi

Les livraisons PC utilisent Python 3.15 et `requirements-build.lock`, avec
versions et empreintes vérifiées. Les dépendances directes restent lisibles
dans les fichiers `requirements*.txt`. Le relais utilise une image Python
figée par digest et des dépendances Gunicorn vérifiées par empreinte. Les
actions GitHub sont figées par commit ; Android conserve ses versions Gradle,
plugins et bibliothèques explicites.

Pour actualiser les dépendances, régénérer les verrous dans un changement dédié,
examiner le diff, exécuter les tests et reconstruire les vrais paquets Windows,
Linux et Android. Les manifestes d’artefacts et leurs SHA restent nécessaires :
une installation reproductible de dépendances ne garantit pas à elle seule
un binaire identique octet pour octet sur un autre système.

Le diagnostic PC indique le protocole de partage, le coffre sélectionné et les
compteurs de capacité du dernier échange avec le relais. Il ne contient aucune
clé, contenu documentaire, recherche saisie ou ligne tarifaire.

Les tests couvrent notamment deux processus concurrents, arrêt et reprise,
transmissions répétées, mauvais espace, révocation d’un appareil, documents
partagés, historique volumineux, suppression après pagination, quota concurrent
et reprise de cache. La CI valide Windows/Linux et Android 10/16. Le partage
SMB/NFS réel et les téléphones de l’établissement restent une validation de
terrain avant déploiement ; les tests locaux ne certifient pas leur configuration.
