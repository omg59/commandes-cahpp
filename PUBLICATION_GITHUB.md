# Publication de Commandes CAHPP sur GitHub

Ce dossier est un dépôt Git complet reconstruit à partir de toutes les
archives conservées pendant le développement. Il contient les versions taguées
de `v0.1` à `v1.1.0`.

## Repartir proprement après la première publication

Si l'ancien dépôt vient juste d'être créé et que personne d'autre ne l'utilise :

1. supprimer l'ancien dépôt GitHub ;
2. recréer un dépôt privé vide nommé `commandes-cahpp` ;
3. ne pas ajouter de README, de `.gitignore` ni de licence depuis GitHub ;
4. extraire entièrement l'archive fournie ;
5. ouvrir GitHub Desktop ;
6. choisir **File > Add local repository** ;
7. sélectionner le dossier `CommandesCAHPP-GitHub-complet` ;
8. vérifier que la branche affichée est `main` ;
9. cliquer sur **Push origin**.

Le dépôt local est préconfiguré pour :

`https://github.com/omg59/commandes-cahpp.git`

## Versions disponibles

| Tags | Contenu |
| --- | --- |
| `v0.1` à `v0.4` | Premiers prototypes |
| `v0.6` et `v0.6.1` | Gestion enrichie des commandes et correctif |
| `v0.7.0` | Améliorations de l'interface |
| `v0.8.0` à `v0.8.1b` | Catalogue, historique et préparation des mails |
| `v0.9.0` | Collaboration par dossier partagé |
| `v1.0.0-rc1` à `v1.0.0-rc5` | Candidats de publication et correctifs |
| `v1.0.0` | Première version stable |
| `v1.0.1` | Correctif de l'icône des raccourcis |
| `v1.1.0` | Livraisons, statistiques, archivage et maintenance |

La version 0.5 n'a jamais été publiée. Cette absence dans la numérotation
est donc normale.

## Données exclues

Le dépôt ne contient aucune base SQLite de travail, commande réelle, pièce
jointe, sauvegarde, export ni environnement Python local. Ces données restent
exclues par `.gitignore`.
