# Commandes CAHPP Horizon — 2.0.0a2

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

Sous Linux, installer `requirements-horizon.txt` dans un environnement Python,
puis lancer `python main_horizon.py`.

## Profils et reprise des données

Le premier lancement crée une démonstration fictive dans
`%LOCALAPPDATA%/CommandesCAHPP-Horizon/demonstration` sous Windows, ou
`$XDG_DATA_HOME/CommandesCAHPP-Horizon/demonstration` sous Linux
(`~/.local/share` par défaut).

**Copier une base 1.6…** crée un nouveau profil autonome. La base source est
ouverte en lecture seule et copiée avec son journal WAL ; elle n'est jamais
utilisée comme base de travail. Les PDF, pièces jointes et le logo accessibles
sont copiés et leurs liens réécrits dans le nouveau profil. Les documents absents
restent signalés comme indisponibles. Le marqueur du profil conserve le nombre
de fichiers copiés ou absents.

La copie reçoit un nouvel identifiant utilisateur. Le partage et le dossier PDF
de la source sont désactivés/effacés dans cette copie. L'activation ultérieure
dans **Paramètres → Collaboration** est un choix explicite ; elle est ensuite
conservée entre les lancements. Les anciens profils alpha 1 restent reconnus.

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

Le bouton **Diagnostic** est accessible dans la barre supérieure et les paramètres.

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
et démarre l'EXE pour vérifier les ressources françaises. La validation manuelle
du poste Windows et du partage de l'établissement reste à effectuer avant un
remplacement du logiciel utilisé au quotidien.

## Identité LADAPT

Le logo fourni est conservé sans retouche. Les bleus et le jaune proviennent des
supports transmis ; voir `ressources/horizon/NOTICE.txt`. Les thèmes clair/sombre
et les dialogues standard en français restent disponibles.
