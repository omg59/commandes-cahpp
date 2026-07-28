# Commandes CAHPP

Application locale Windows pour importer un catalogue tarifaire CAHPP, retrouver
rapidement les articles, préparer des commandes fournisseurs et générer des bons
de commande PDF.

## Principes

- fonctionnement entièrement local, sans serveur ni compte en ligne ;
- base SQLite conservée dans le dossier `data` ;
- import d'un nouveau fichier Excel CAHPP avec comparaison de la version
  précédente ;
- conservation des tarifs historiques et des lignes de commandes déjà créées ;
- recherche par fournisseur, code CAHPP, référence ou désignation ;
- favoris et quantités habituelles ;
- bon PDF commun à tous les fournisseurs.

## Lancement depuis les sources

Python 3.11 ou 3.12 est recommandé.

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

## Création du dossier portable Windows

Depuis un poste Windows 11 64 bits :

```bat
build_windows.bat
```

Le résultat se trouve dans `dist\CommandesCAHPP-portable`. Ce dossier peut être
copié sur un autre poste. Les données restent dans
`data\commandes_cahpp.sqlite3`, à côté de l'application.

## Sauvegarde

Fermer l'application, puis copier le fichier
`data\commandes_cahpp.sqlite3`. Les PDF sont enregistrés dans `exports`.

## Première utilisation

1. Ouvrir **Paramètres** et renseigner l'établissement.
2. Le paquet fourni contient déjà le catalogue transmis lors de la création du
   prototype. Pour une version plus récente, ouvrir **Mise à jour CAHPP** et
   sélectionner le nouvel Excel.
3. Configurer les fournisseurs utilisés : numéro client, adresse e-mail et
   montant du franco.
4. Marquer les articles habituels comme favoris.
5. Préparer une commande et générer le PDF.

La liste des fournisseurs de l'écran **Nouvelle commande** est filtrée pendant
la saisie du nom. Depuis **Catalogue**, sélectionner un article puis cliquer sur
**Commander cet article** pour ouvrir directement une commande avec le bon
fournisseur.

## Personnalisation du PDF

Dans **Paramètres**, il est possible de modifier :

- le nom, l'adresse et les identifiants de l'établissement ;
- le logo ;
- le titre du document ;
- le texte du pied de page, qui peut rester vide ;
- l'affichage du numéro de page.
- le dossier proposé par défaut lors de l'enregistrement.

Lors de chaque génération ou régénération, une fenêtre **Enregistrer sous**
permet de modifier librement le nom et la destination du PDF.

Le nom proposé suit le format :

```text
BC-AAAA-MM-JJ_Fournisseur.pdf
```

S'il existe plusieurs commandes le même jour pour le même fournisseur, le
compteur est ajouté automatiquement :

```text
BC-2026-07-28_Hartmann.pdf
BC-2026-07-28_2_Hartmann.pdf
BC-2026-07-28_3_Hartmann.pdf
```

## Modifier un brouillon

1. Ouvrir **Historique**.
2. Sélectionner une commande ayant le statut **Brouillon**.
3. Cliquer sur **Modifier le brouillon** ou double-cliquer sur la ligne.
4. Modifier les articles, quantités ou la note.
5. Enregistrer à nouveau le brouillon ou générer le PDF.

Une commande déjà générée reste figée. Cela évite de modifier par erreur un bon
qui aurait déjà été envoyé au fournisseur.

## Limitation du prototype

L'exécutable Windows doit être compilé sur Windows : PyInstaller ne permet pas
de produire de manière fiable un `.exe` Windows depuis Linux. Le script
`build_windows.bat` automatise entièrement cette compilation. L'application
obtenue fonctionne ensuite sans Python et sans connexion Internet.
