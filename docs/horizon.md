# Commandes CAHPP Horizon — 2.0.0a1

Horizon est la première interface Qt de Commandes CAHPP. La branche
`feature/horizon-ui` développe cette version en parallèle de la 1.6.0.
Cette alpha sert aux essais locaux ; elle n'est pas destinée à remplacer la
version utilisée en production sur les deux postes.

## Démarrer

Sous Windows, double-cliquer sur **`horizon_windows.bat`** pour lancer les sources.
Python 3.12 64 bits et Internet sont nécessaires à la première installation des
dépendances. La commande **`horizon_windows.bat build`** exécute les contrôles et
fabrique `dist/CommandesCAHPP-Horizon-portable/CommandesCAHPP-Horizon.exe`.
Conserver le dossier `_internal` à côté de l'EXE. Le dossier compilé s'utilise
ensuite sans Python. Il ne faut pas remplacer l'EXE de la version 1.6.0.

Sous Linux, créer et activer un environnement virtuel, installer
`python -m pip install -r requirements-horizon.txt`, puis lancer
`python main_horizon.py`. Qt utilise le système graphique local.

## Profils et données

Le premier lancement crée une démonstration avec huit articles et des commandes
fictives. Le profil est stocké dans `%LOCALAPPDATA%/CommandesCAHPP-Horizon`
sous Windows, ou `$XDG_DATA_HOME/CommandesCAHPP-Horizon` sous Linux
(`~/.local/share/CommandesCAHPP-Horizon` par défaut).

Le bouton **Copier une base 1.6…** permet de sélectionner
`commandes_cahpp.sqlite3` de l'installation habituelle. Une copie cohérente est
effectuée en lecture seule, puis ouverte dans une nouvelle fenêtre avec son
propre profil. Elle inclut les données validées du journal WAL. La source n'est
jamais ouverte par Horizon comme base de travail. Chaque copie reçoit un
nouveau dossier ; la démonstration et les copies précédentes sont conservées.

Les documents historiques ne sont pas recopiés avec la base. Leurs chemins sont
conservés, mais ils ne sont pas forcément disponibles dans le profil. Les
nouveaux PDF, exports, sauvegardes et journaux sont écrits dans le profil Horizon.
La suppression d'une commande dans Horizon ne supprime pas les PDF exportés.

Pour réouvrir une copie depuis les sources :
`python main_horizon.py --profile "chemin/du/profil"`.
Pour créer une copie depuis la ligne de commande :
`python main_horizon.py --copy-database "chemin/commandes_cahpp.sqlite3"`.
Un dossier existant sans marqueur Horizon est refusé comme profil de travail.
`CAHPP_HORIZON_ROOT` permet de choisir un autre dossier de profils d'essai.

## Fonctions déjà disponibles

- Accueil : préparations non envoyées, livraisons en attente, montant HT envoyé
  ce mois et articles à vérifier, avec accès aux commandes récentes.
- Catalogue : recherche FTS5 en arrière-plan, sélection fournisseur, favoris,
  références inactives, fiche latérale et contrôle des conditionnements.
  Seules 100 lignes sont chargées initialement ; affichage progressif jusqu'à
  1 000 résultats avant de demander une recherche plus précise.
- Import : catalogues complets et évolutions mensuelles, aperçu et confirmations,
  sauvegarde préalable et transaction du moteur 1.6.0.
- Préparation : un fournisseur par commande, quantités modifiables dans le panier,
  totaux décimaux, franco, notes, service destinataire, brouillon et bon PDF.
- Historique : recherche, reprise des commandes non envoyées, suppression
  autorisée par le moteur et marquage de l'envoi effectué hors de l'application.
- Statistiques : courbe mensuelle, barres par fournisseur sélectionnables,
  périodes de 3/6/12 mois et détail des montants et délais. Les brouillons sont
  exclus ; seuls les bons dont l'envoi est enregistré sont comptabilisés.
- Thèmes clair/sombre et textes français, y compris les dialogues standard Qt.

## Ce qui reste à porter

La collaboration et les verrous partagés, les réceptions détaillées, les pièces
jointes, la préparation des messages, les recommandations et les réglages métier
complets restent dans la version stable. La collaboration est désactivée dans
tous les profils de cette alpha ; aucun catalogue ni aucune commande Horizon
n'est publié sur le dossier partagé.

## Architecture et validation

`main_horizon.py` configure les chemins avant de charger le moteur. Le paquet
`cahpp_app/horizon` sépare profils, services, travaux asynchrones, modèles de
tableaux et écrans. Les services réutilisent `Database`, `CatalogImporter` et
`generate_order_pdf`. Le schéma reste 15, sans migration spécifique à Horizon.
`CAHPP_RESOURCE_ROOT` sépare les ressources livrées des données du profil.

Les calculs du panier utilisent `Decimal` et les mêmes arrondis intermédiaires
que `Database.save_order`. L'enregistrement et la génération PDF appliquent les
garde-fous sur les références inactives et les contrôles de catalogue en attente.
Les workers ne détiennent aucun widget ; les résultats sont transmis au thread
Qt par signaux en connexion différée. Une recherche remplacée est annulée et
son résultat ignoré. La fermeture attend la fin des travaux annulés.

Les tests couvrent l'isolation des profils, la copie avec WAL, le panier,
l'exclusion des brouillons dans les graphiques et le parcours Qt catalogue,
vérification, brouillon, PDF et réouverture. La CI Horizon vérifie les deux
systèmes et produit un dossier Windows téléchargeable dans les artefacts du run.

Un essai Qt sur un catalogue fictif de 158 488 articles a vérifié les limites
de 100 puis 200 lignes, les recherches successives et la réactivité du thread
graphique. Sur l'environnement Linux d'essai, la recherche d'une référence a
pris environ 450 ms, avec un intervalle maximal de 31 ms entre deux passages
du minuteur graphique. Ces mesures ne préjugent pas des temps sur chaque PC.

## Identité LADAPT

Le logo fourni est conservé sans retouche. Les bleus et le jaune sont repris des
supports transmis ; voir `ressources/horizon/NOTICE.txt`. Les polices du projet
associatif ne sont pas embarquées. Cette première adaptation visuelle pourra
être affinée avec la charte officielle et les retours d'usage.
