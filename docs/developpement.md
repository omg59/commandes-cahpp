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
4. Exécuter les tests et le lint, puis compiler `build_installer_windows.bat`.
5. Vérifier le démarrage de l'EXE, l'installation et la conservation des données
   sur une installation de test ; consigner les résultats de validation.
6. Publier les changements, vérifier GitHub Actions puis créer, si nécessaire,
   un tag et une release pointant sur le commit validé.
7. Déposer uniquement l'installateur validé dans le sous-dossier partagé
   `mises-a-jour` pour le proposer aux postes utilisateurs.

Ne plus créer de checklist ou de notice séparée pour chaque version. Le
changelog conserve l'historique, les guides décrivent le fonctionnement courant.
Les anciens fichiers supprimés restent consultables dans l'historique Git.

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
