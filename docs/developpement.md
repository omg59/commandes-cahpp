# Développement et publication

## Sources et compilation

Le dépôt de référence est [omg59/commandes-cahpp](https://github.com/omg59/commandes-cahpp).
Le [README](../README.md) décrit le lancement depuis les sources et les scripts
de compilation Windows. Le poste de compilation utilise Python 3.12 64 bits
et Inno Setup 6 ou 7. Les postes utilisateurs n'ont pas besoin de Python.

Installer les dépendances de développement avec
`python -m pip install -r requirements-dev.txt`, puis suivre les
[contrôles automatiques et manuels](validation.md).

## Préparer une version

1. Mettre à jour la version dans `cahpp_app/__init__.py`, `CommandesCAHPP.iss`,
   le nom de l'installateur affiché dans `build_installer_windows.bat` et le README.
2. Ajouter une entrée dans [CHANGELOG.md](../CHANGELOG.md).
3. Mettre à jour les guides concernés et la checklist commune si nécessaire.
4. Lancer `build_release.bat` sous Windows : cohérence des versions, lint,
   tests graphiques, compilation puis manifeste SHA-256 de l'installateur.
5. Vérifier le démarrage de l'EXE, l'installation et la conservation des données
   sur une installation de test ; consigner les résultats de validation.
6. Publier les changements, vérifier GitHub Actions puis créer, si nécessaire,
   un tag et une release pointant sur le commit validé.
7. Déposer uniquement l'installateur validé dans le sous-dossier partagé
   `mises-a-jour` pour le proposer aux postes utilisateurs.

Ne plus créer de checklist ou de notice séparée pour chaque version. Le
changelog conserve l'historique, les guides décrivent le fonctionnement courant.
Les anciens fichiers supprimés restent consultables dans l'historique Git.

`python tools/release_checks.py` vérifie les versions sans compiler.
L'option `--manifest` exige l'installateur correspondant dans `dist-installer`
et écrit sa taille et son empreinte dans un manifeste JSON et un fichier
`.sha256`. Une empreinte sert à contrôler le fichier diffusé ; elle ne remplace
pas la validation de son installation.

## Organisation du code

L'interface est un paquet `cahpp_app/ui/`. Son `__init__.py` préserve les
imports publics, notamment `App`. Chaque onglet possède son module :
`catalog.py`, `order.py`, `history.py`, `suppliers.py`, `settings.py`,
`dashboard.py`, `statistics.py`, `suggestions.py` et `import_catalog.py`.
Les dialogues de documents et de suivi sont dans `documents.py` et
`tracking.py`. `components.py`, `common.py` et `base.py` regroupent les éléments
partagés ; `app.py` orchestre navigation et collaboration.

Les recherches SQLite utilisent `catalog_search.py`. `ui/search.py` apporte
la passerelle vers Tk : le worker dépose ses résultats dans une file, puis
le thread principal les consomme. Les autres workers utilisent `App.post_ui`.
Ne pas appeler Tk, même `after()`, depuis un thread de travail.

La réparation d'index utilise un savepoint SQLite, y compris pendant un import.
Seule la table dérivée `product_search` est recréée ; elle est validée par la
commande FTS5 `integrity-check` et par la requête MATCH avec classement utilisée
pour les recherches. Une erreur annule le savepoint. Le diagnostic ne lance
aucune réparation automatique : le bouton explicite la déclenche dans un worker.
La dernière tentative est conservée dans l'objet `Database` pendant la session.

La 1.5.2 actualise `ANALYZE products` et `ANALYZE product_overrides` une fois
par session/catalogue, dans le worker de recherche ou de diagnostic. Des
statistiques datant d'une petite base peuvent inciter SQLite à boucler sur
tous les produits et réexécuter MATCH pour chacun. La jointure FTS → produits
utilise aussi `CROSS JOIN` pour fixer cet ordre. Les statistiques exactes restent
nécessaires pour obtenir une lecture par clé primaire dans la table produits.
Les tests mesurent un budget d'instructions SQLite plutôt qu'un délai matériel.

`numbers.py` centralise conversion et affichage décimal. Les données existantes
restent compatibles ; le stockage monétaire n'est pas modifié.
`database.py` conserve la persistance ; son découpage par domaine et l'audit
complet des montants feront l'objet de travaux distincts.

## Contrat d'import CAHPP

`catalog_importer.py` conserve les imports publics existants. Le paquet
`catalog_import/` sépare les responsabilités : `formats.py` décrit les alias,
les types d'import et les validations ; `engine.py` prépare une table temporaire
sur disque puis applique une transaction ; `snapshots.py` exporte l'état CAHPP
complet pour le partage. Les lignes du classeur ne sont jamais toutes chargées
dans une liste Python. Les champs texte des instantanés restent littéraux même
lorsqu'ils ressemblent à une formule Excel.

`inspect_file(path)` ne modifie aucune donnée métier et retourne un
`ImportPreview`. `import_file(path, options=ImportOptions(...), preview=...)`
recontrôle l'empreinte et la politique sous `BEGIN IMMEDIATE`. Les confirmations
de base initiale, révision mensuelle et remplacement sont explicites. Sans
options, un appel programmatique refuse toute opération nécessitant confirmation.
Une erreur de lecture, de fusion ou de reconstruction FTS annule la transaction.
Les identifiants produits, corrections et anciennes commandes sont conservés.

Les colonnes sont normalisées par alias explicites, sans correspondance floue.
Un fichier ambigu, une colonne requise absente, un code dupliqué ou un statut
inconnu sont refusés avant fusion. Des colonnes supplémentaires sont tolérées.
Pour étendre le format, ajouter les alias et un test de contrat ; ne pas inventer
les quantités depuis le texte ni traiter un fichier partiel comme une base complète.
Les types d'évolution inconnus sont importés avec vérification obligatoire.
Les anciens catalogues complets peuvent contenir une colonne réservée
`ARTICLEACTIF` entièrement vide : la présence d'une référence conserve alors
le sens historique « actif ». Cette exception ne concerne ni les deltas ni les
instantanés, pour lesquels un statut absent reste une erreur.

Le schéma 15 ajoute les métadonnées d'import, jetons de contrôle et validations
associées. Le jeton lie une confirmation à une évolution précise et voyage dans
les instantanés ; la validation voyage dans les corrections d'équipe. La
validation des lignes est aussi effectuée dans la transaction d'enregistrement
des commandes et avant génération d'un PDF de brouillon.

Le format partagé 2 utilise un instantané `commandes-cahpp-catalogue-v1`, une
feuille `CAHPP_META` et la version minimale 1.6.0. La colonne `CODE_CAHPP` fait
refuser l'instantané aux anciens lecteurs qui exigent littéralement `CodeCahpp`.
Après import mensuel, publier uniquement un état complet cohérent avec le dernier
import local. Le manifeste stocke l'empreinte de l'instantané et celle du fichier
source, le mois courant et les comptages. Le fichier source mensuel est archivé.
Le verrou partagé couvre l'import et la publication ; la publication vérifie
également que le catalogue distant est toujours celui sur lequel reposait le delta.

L'interface gère l'aperçu, les confirmations et la sauvegarde complète préalable
dans son worker, avec les dialogues Tk dans le thread principal. Le moteur
programmatique reste transactionnel mais ne crée pas de ZIP automatiquement.
Ne pas utiliser les noms d'attributs réservés par Tk, notamment `_options`.

## Utiliser GitHub Desktop

1. Cloner le dépôt une première fois ou ouvrir le clone existant.
2. Faire **Fetch origin**, puis **Pull origin** si des changements sont disponibles.
3. Modifier les sources ; si elles viennent d'une archive, copier les fichiers
   concernés en tenant compte des suppressions et des renommages. Ne pas
   remplacer le dossier `.git` du clone.
4. Contrôler le diff, créer un commit puis utiliser **Push origin**.
5. Vérifier les résultats dans [Actions](https://github.com/omg59/commandes-cahpp/actions).

Une archive de sources n'est pas un dépôt Git complet et n'emporte pas de tags.
Ne pas recréer le dépôt ou réécrire son historique pour une mise à jour ordinaire.

## Données à exclure

Ne pas versionner les bases SQLite, catalogues CAHPP Excel, commandes réelles,
PDF, pièces jointes, sauvegardes, logs, identifiants ou coordonnées métier.
Contrôler le diff même lorsque `.gitignore` est présent. Conserver la licence
des polices dans `ressources/DEJAVU-LICENSE.txt` et les icônes de l'application.

## Organisation de la documentation

- [README](../README.md) : présentation, installation et utilisation.
- [Changelog](../CHANGELOG.md) : changements par version.
- [Collaboration](collaboration.md) : installation à plusieurs postes et reprise réseau.
- [Validation](validation.md) : tests automatiques, checklist et prochaines étapes.
- Ce guide : développement, compilation et publication.
