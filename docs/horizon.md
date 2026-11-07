# Commandes CAHPP Horizon — 2.0.0a9

Horizon reprend les fonctions métier de Commandes CAHPP 1.6.0 dans une interface
Qt/PySide6 aux couleurs LADAPT. Le développement reste sur la branche
`feature/horizon-ui`. Le moteur conserve la version 1.6.0 et le schéma 15 :
la version stable et son installateur restent distincts.

## Démarrer et installer

Sous Windows, `horizon_windows.bat` lance les sources avec Python 3.12.
`horizon_windows.bat build` valide puis construit le dossier portable
`dist/CommandesCAHPP-Horizon-portable`. Conserver `_internal` avec l'EXE.
`build_horizon_installer.bat` construit en plus un installateur avec Inno Setup 6
ou 7, sans droits administrateur, dans `dist-installer-horizon`.

L'installation Horizon utilise un identifiant et un dossier programme distincts
de la 1.6.0. Les mises à jour remplacent le programme ; les profils et documents
sont conservés. La CI fournit le dossier portable Windows après validation.

### Linux : AppImage et portable

Dans la [page Actions Horizon](https://github.com/omg59/commandes-cahpp/actions/workflows/horizon.yml),
ouvrir le dernier run vert de la branche `feature/horizon-ui`, puis télécharger
l'artefact **CommandesCAHPP-Horizon-Linux-x86_64**. GitHub demande d'être connecté
pour télécharger les artefacts. Le ZIP contient :

- `CommandesCAHPP-Horizon-2.0.0a9-x86_64.AppImage` : l'application en un fichier ;
- `CommandesCAHPP-Horizon-2.0.0a9-x86_64.tar.gz` : variante portable à décompresser ;
- `SHA256SUMS` et le manifeste JSON de construction.

Après extraction du ZIP, rendre l'AppImage exécutable dans les propriétés du
fichier ou utiliser :

```bash
chmod +x CommandesCAHPP-Horizon-2.0.0a9-x86_64.AppImage
./CommandesCAHPP-Horizon-2.0.0a9-x86_64.AppImage
```

Python et Qt sont inclus. Les données restent dans le même profil Linux que le
lancement depuis Python ; remplacer le fichier AppImage conserve les réglages,
commandes et documents. Il n'y a pas de paquet à installer ni de droit
administrateur requis pour lancer l'application.

Si FUSE est indisponible, lancer l'AppImage avec `--appimage-extract-and-run`.
La variante tar.gz fonctionne aussi : extraire l'archive puis lancer **AppRun**.
Le format tar conserve les permissions et les liens internes nécessaires au
programme, contrairement à un ZIP ordinaire du dossier compilé.

Les builds officiels ciblent Linux **x86_64 avec glibc 2.35 ou ultérieure** :
Ubuntu 22.04+, Debian 12 et distributions récentes comme CachyOS. Le bureau,
les pilotes graphiques et les bibliothèques système de base restent fournis par
Linux. Il ne s'agit pas d'une version ARM ni d'un paquet pour les systèmes musl.

### Construire sur Linux

Depuis des sources à jour, exécuter `bash build_horizon_linux.sh`. Le script crée
un environnement de compilation, installe les dépendances Python, valide les
tests, construit le programme et produit les deux paquets dans `dist-linux`.
Python 3.11/3.12 avec `venv` et une connexion Internet sont nécessaires pour la
construction uniquement. Les paquets obtenus se lancent sans Python installé.

La construction est native : sous un Linux plus récent que celui de la CI,
le résultat peut demander une glibc plus récente. Pour diffuser le paquet,
utiliser de préférence le build CI Ubuntu 22.04. Les versions des outils
AppImage et du runtime sont figées et leurs empreintes vérifiées ; le constructeur
les extrait pour fonctionner même sans FUSE.

Le constructeur vérifie aussi les dépendances du plugin graphique X11 et la
présence des bibliothèques de curseur et de forme XCB dans le paquet. Sous
Ubuntu, les paquets de compilation comprennent notamment `libxcb-cursor0` et
`libxcb-shape0` ; sous Arch/CachyOS, les bibliothèques correspondantes sont
fournies par `xcb-util-cursor` et `libxcb`. Une dépendance absente arrête le build
avant la fabrication d'un AppImage incomplet.

Pour le développement, le lancement direct reste possible après installation de
`requirements-horizon.txt`, avec `python main_horizon.py`.

## Profils et reprise des données

Le premier lancement crée une démonstration fictive dans
`%LOCALAPPDATA%/CommandesCAHPP-Horizon/demonstration` sous Windows, ou
`$XDG_DATA_HOME/CommandesCAHPP-Horizon/demonstration` sous Linux
(`~/.local/share` par défaut).

Dans **Paramètres → Maintenance**, **Copier une base 1.6…** crée un nouveau profil autonome. La base source est
ouverte en lecture seule et copiée avec son journal WAL ; elle n'est jamais
utilisée comme base de travail. Les PDF, pièces jointes et le logo accessibles
sont copiés et leurs liens réécrits dans le nouveau profil. Les documents absents
restent signalés comme indisponibles. Le marqueur du profil conserve le nombre
de fichiers copiés ou absents.

La copie reçoit un nouvel identifiant utilisateur. Le partage et le dossier PDF
de la source sont désactivés/effacés dans cette copie. L'activation ultérieure
dans **Paramètres → Collaboration** est un choix explicite ; elle est ensuite
conservée entre les lancements. Les anciens profils alpha 1 restent reconnus.

La copie conserve les fiches fournisseurs (numéro client, coordonnées, franco,
minimum, notes), favoris, réglages d'établissement, identité, modèles PDF/e-mail
et historique. Le logo personnalisé de l'établissement est distinct du logo de
l'application. Les documents accessibles sont dupliqués sans modifier la source.

La mise à jour entre versions Horizon utilise le même installateur Horizon et
conserve les profils. Le passage depuis la 1.6.0 est actuellement une **migration
par copie**, avec installation des deux applications côte à côte. L'installateur
d'essai ne remplace pas une installation 1.6.0. Une mise à niveau directe de la
version stable devra être préparée pour la diffusion finale de la 2.0.

## Commande et confort d'utilisation

La barre latérale regroupe les parcours dans **Commandes** :
**Nouvelle commande**, **Suivi des commandes** et **À recommander**. Le changement
d'onglet conserve la commande en cours et les filtres. Un retour par le bouton
latéral retrouve le dernier onglet consulté ; les raccourcis depuis le catalogue
et l'accueil ouvrent directement l'onglet concerné.

**Nouvelle commande** présente les articles avec deux colonnes séparées,
**Référence** et **Désignation**, sans répéter le fournisseur sélectionné.
Le panneau **Ma commande**, élargi et redimensionnable, conserve également ces
deux colonnes ; les quantités restent éditables dans la colonne **Cartons**.
Les listes de fournisseurs acceptent la saisie d'un nom ou d'une partie du nom.
Il faut choisir un résultat existant ; une saisie partielle n'est pas utilisée
comme fournisseur d'une commande.

Les dates s'affichent et se saisissent en **JJ/MM/AAAA**, par exemple
**07/11/2026** : préparation, historique, date de livraison prévue, réceptions,
statistiques, imports, documents, notes internes et paramètres. Les horodatages
affichent aussi l'heure en format 24 h. Les tableaux gardent leur tri chronologique.
Une ancienne date ISO collée dans un champ reste acceptée et est réaffichée en
français. Le stockage SQLite et les échanges du partage restent au format ISO.
Les noms de PDF et d’exports utilisent **AAAA-MM-JJ** pour faciliter le tri dans
l’explorateur. Les dates des exports Excel utilisent aussi le format **AAAA-MM-JJ**,
avec de vraies cellules de date. Les fichiers existants ne sont pas renommés.

Le bouton **Valider et générer le PDF…** crée le bon puis ouvre directement la
fenêtre **Envoyer la commande au fournisseur**. Elle affiche le destinataire,
le numéro, le montant et le PDF. **Envoyer l'e-mail au fournisseur** prépare le
message selon les modèles enregistrés et ouvre le dossier du PDF et des autres
documents cochés pour l'e-mail. Joindre ces fichiers puis envoyer depuis la
messagerie : une composition web ne permet pas de joindre automatiquement des
fichiers locaux. **J'ai envoyé la commande** confirme ensuite l'envoi, ferme la
fenêtre et libère le panier, sans passer par l'historique.
Après la première ouverture réussie, le bouton devient
**Envoyer à nouveau l'e-mail au fournisseur**. Ce libellé est conservé lors de la
reprise d'un e-mail déjà préparé. Le dossier des pièces jointes garde son libellé.

**Plus tard** conserve la commande générée. Le bouton **Envoyer cette commande…**
permet de reprendre depuis la préparation ; l'historique propose aussi un bouton
direct **Envoyer au fournisseur…**. Un message déjà préparé peut être confirmé
sans le rouvrir. Annuler la génération du PDF ou rencontrer une erreur de création
n'ouvre pas la fenêtre d'envoi. Ouvrir la messagerie ne marque jamais la commande
comme envoyée.

Les fiches fournisseurs sont dans **Paramètres → Fournisseurs**, à côté de
**Établissement** : coordonnées, e-mail, numéro client, minimum, franco et notes.
La fiche conserve son propre bouton **Enregistrer la fiche** et protège les
modifications non enregistrées. Si l'adresse manque dans la fenêtre d'envoi,
un raccourci ouvre la fiche du fournisseur concerné ; la commande et le PDF sont
conservés.

La barre supérieure contient la recherche rapide et l'interrupteur soleil/lune
pour les modes clair/sombre. Le choix est mémorisé dans le profil. Les actions
de reprise de base et de diagnostic sont uniquement dans les paramètres.

Le logo de l'application et les titres sont centrés dans la barre latérale.
Le logo LADAPT fourni est affiché en bas sans retouche, avec ses proportions
conservées. **Paramètres → À propos** indique l'auteur **Damien Macq**, la version,
les crédits et les informations sur les données et composants tiers. Le bouton
**Notices et licences…** permet de consulter les textes joints à l'application.

Pour rouvrir une copie : `python main_horizon.py --profile "chemin/du/profil"`.
Pour créer une copie : `python main_horizon.py --copy-database "chemin/base.sqlite3"`.
`CAHPP_HORIZON_ROOT` change le dossier des profils d'essai. Un dossier existant
sans marqueur Horizon est refusé.

## Fonctions de la 1.6.0 dans Horizon

| Domaine | Fonctions disponibles |
| --- | --- |
| Accueil | Brouillons, dépenses envoyées, livraisons, contrôles catalogue, confirmations manquantes et retards configurables. |
| Catalogue | Recherche asynchrone FTS5, fournisseurs, favoris, inactifs, pagination, tri, corrections et validation des conditionnements. |
| Articles | Quantités habituelles, nom court, notes internes, remplacement, création/modification/archivage des articles hors catalogue et retour aux valeurs CAHPP. |
| Préparation | Un fournisseur par commande, date, service, notes, panier décimal, quantités éditables, minimum/franco/cartons fractionnés et détection de commande similaire. |
| PDF | Identité de l'établissement, logo, titre, pied de page, numéros de page, dossier par défaut, choix du fichier et régénération historique. |
| Historique | Recherche complète, statuts/livraisons, filtres enregistrés, archives, reprise avec le même numéro, suppression avant envoi, duplication complète ou sélective. |
| Suivi | Confirmation fournisseur, date prévue, réceptions partielles en unités, reliquats, annulation des réceptions, livraison et facturation. |
| Documents | Plusieurs fichiers typés par commande, ouverture, propriétés, inclusion dans la préparation d'e-mail, retrait et copie locale. |
| Notes et audit | Notes internes partagées et historique daté des actions avec leur auteur. |
| E-mail | Modèles paramétrables, dossier de préparation PDF/pièces jointes et ouverture de la composition sans envoi automatique. |
| Recommandations | Rythme historique des commandes envoyées et préparation d'une sélection d'articles d'un fournisseur. |
| Statistiques | Périodes et dates libres, fournisseur, graphiques, achats par article, comparaison des prix, délais et export Excel de la sélection affichée. |
| Import CAHPP | Catalogue complet, évolution mensuelle et instantané partagé ; aperçu, confirmations, chronologie, sauvegarde préalable, transaction et suivi des changements. |
| Fournisseurs | Numéro client, contact, e-mail, téléphone, adresse, site, franco, minimum et notes ; protection des saisies non enregistrées. |
| Collaboration | Synchronisation manuelle/périodique, données d'équipe, commandes/documents, catalogue partagé, numérotation et verrous. |
| Maintenance | Sauvegarde ZIP complète, rappels, contrôle d'intégrité périodique, archivage manuel/automatique et mises à jour Horizon depuis le partage. |
| Diagnostic | SQLite, index FTS, plan de recherche, reconstruction, partage, synchronisation, verrous, journaux et export texte. |

Les statistiques excluent les brouillons. Les anciennes lignes de commande
conservent leurs prix et conditionnements. Le marquage « envoyée » confirme
un envoi effectué par l'utilisateur ; préparer un e-mail ne l'envoie jamais.

## Collaboration

La base reste locale ; seul le dossier choisi est partagé. La synchronisation
et le format de fichiers sont ceux de la 1.6.0. Une préparation existante conserve
son verrou jusqu'à sa fermeture ; un verrou perdu interdit l'enregistrement.
Les écritures sont refusées si une synchronisation/maintenance est en cours.
Un partage inaccessible laisse la consultation et le diagnostic disponibles ;
les modifications qui nécessitent un verrou sont bloquées.

La pause pendant les saisies non enregistrées est configurable. Les formulaires
modifiés ne sont jamais remplacés par un rafraîchissement. Les changements de
fournisseur détectent aussi une révision locale plus récente.

**Mise à jour CAHPP** permet d'appliquer le nouveau catalogue partagé. Un import
local est sauvegardé avant application et publié sous verrou de catalogue.
L'instantané reçu est contrôlé, installé puis marqué appliqué sans republier
un nouveau catalogue.

Horizon ne propose que les installateurs
`CommandesCAHPP-Horizon-Setup-X.Y.Z[aN|bN|rcN].exe` déposés dans
`mises-a-jour`. Les installateurs de la version stable sont ignorés.

## Diagnostics et débogage

Le bouton **Diagnostics et débogage** est accessible uniquement dans **Paramètres**.

- **Actualiser** exécute les contrôles en arrière-plan : intégrité SQLite,
  schéma, FTS5, cohérence des entrées, recherche avec classement, statistiques et
  plan du moteur, accès au partage, catalogue, synchronisation et verrous.
- **Reconstruire l'index** est une action explicite : seule la table dérivée
  FTS est reconstruite, vérifiée puis validée. Le rapport conserve la dernière
  tentative, sa durée et les informations d'erreur.
- **Copier** et **Exporter** donnent le rapport texte ; les journaux restent
  accessibles par **Ouvrir les journaux**.
- Le rapport identifie Horizon, Qt/PySide6, le profil et la dernière synchronisation,
  sans exporter les tarifs, recherches saisies, notes ou lignes de commande.

## Validation

Les tests conservent la suite du moteur 1.6.0. Les tests Horizon couvrent les
profils, WAL, copies de documents, montants, catalogue, PDF et réouverture ; le
parcours Qt complet visite les réglages, fournisseur, réceptions, pièces jointes,
notes, duplication, export Excel, sauvegarde et diagnostic/réparation.

Des essais avec deux bases et un partage réel contrôlent les conflits de verrou,
la numérotation, la perte de réservation, les réceptions synchronisées, la
facturation et la publication/application d'un catalogue. Les tests hors réseau
vérifient l'accès au diagnostic et le refus des écritures non protégées.

La CI exécute les contrôles sous Linux et Windows, construit le dossier Windows
et l'AppImage Linux puis les démarre pour vérifier les ressources françaises.
Elle vérifie aussi la conservation et la copie d'un profil depuis l'AppImage,
le lancement de l'archive portable et les empreintes des livrables. La validation manuelle
du poste Windows et du partage de l'établissement reste à effectuer avant un
remplacement du logiciel utilisé au quotidien.

## Identité LADAPT

Le logo et les icônes d'application reprennent les fichiers de la version 1.6.0
dans `assets`, sans retouche. Les bleus et le jaune proviennent des supports
LADAPT transmis ; voir `ressources/horizon/NOTICE.txt`. Les thèmes clair/sombre
et les dialogues standard en français restent disponibles.
