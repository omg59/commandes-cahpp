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

`numbers.py` centralise conversion et affichage décimal. Les données existantes
restent compatibles : pas de migration du schéma ni du stockage monétaire.
`database.py` conserve la persistance ; son découpage par domaine et l'audit
complet des montants feront l'objet de travaux distincts.

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
