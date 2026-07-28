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
- duplication des commandes récurrentes ;
- recherche dans tout l'historique, y compris les références et désignations ;
- suivi des changements de prix et de conditionnement des articles commandés ;
- rattachement des bons de livraison et autres documents ;
- préparation des e-mails dans Gmail sans mot de passe ni droit administrateur ;
- sauvegarde complète de la base et des documents liés ;
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

Les favoris du fournisseur sont affichés en premier dans la préparation d'une
commande. En l'absence de recherche, la liste est limitée aux favoris s'il en
existe.

## Personnalisation du PDF

Dans **Paramètres**, il est possible de modifier :

- le nom, l'adresse et les identifiants de l'établissement ;
- le logo ;
- le titre du document ;
- le texte du pied de page, qui peut rester vide ;
- l'affichage du numéro de page ;
- le dossier proposé par défaut lors de l'enregistrement.

Pour un logo portable, placez-le par exemple dans `assets\logo.png` puis
indiquez simplement `assets/logo.png` dans les paramètres.

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

Pour repartir d'une ancienne commande, sélectionnez-la dans **Historique** puis
cliquez sur **Dupliquer**. Un nouveau brouillon daté du jour est créé avec les
prix et conditionnements de la commande d'origine.

## Préparer une commande dans Gmail

Dans **Fournisseurs**, renseignez l'adresse e-mail de commande. Les modèles
d'objet et de message peuvent être modifiés dans **Paramètres** avec les
variables suivantes :

```text
{order_number} {order_date} {supplier} {total_ht}
{establishment_name} {customer_number}
```

Dans **Historique**, le bouton **Préparer dans Gmail** :

1. ouvre un message Gmail avec le destinataire, l'objet et le texte préremplis ;
2. ouvre un dossier contenant le PDF et toutes les pièces marquées
   **Joint au mail** ;
3. permet de joindre l'ensemble par `Ctrl+A`, puis glisser-déposer dans Gmail.

L'ajout final des fichiers reste manuel car Gmail Web interdit à une application
locale de déposer silencieusement des pièces jointes sans autorisation OAuth de
l'organisation. Aucun identifiant ni mot de passe Google n'est enregistré.

## Documents et bons de livraison

Dans **Historique**, sélectionnez une commande puis ouvrez
**Documents / bon de livraison**. Les fichiers choisis sont copiés dans
`documents\<numero de commande>` à côté de l'application. Ils restent ainsi
liés à la commande même si le fichier original du scanner est déplacé.

Une pièce peut être incluse ou exclue de la préparation Gmail. Les bons de
livraison ne sont pas joints au mail par défaut.

## Mise à jour des tarifs

Après l'import d'un catalogue, l'application signale les variations de prix ou
de conditionnement qui concernent des articles déjà commandés. Le détail reste
consultable depuis l'historique des imports. Les anciennes commandes conservent
toujours leurs valeurs d'origine.

## Seuils et conditionnements

Les coordonnées, le minimum de commande et le franco se configurent dans
**Fournisseurs**. Avant l'enregistrement, l'application avertit si :

- le nombre de cartons d'une ligne n'est pas entier ;
- le minimum de commande n'est pas atteint ;
- le franco n'est pas atteint.

L'utilisateur peut confirmer et continuer si le fournisseur accepte une
exception.

## Sauvegarde complète

Le bouton **Exporter une sauvegarde complète**, dans l'onglet **Sauvegarde**
des paramètres, crée une archive ZIP contenant la base SQLite et tous les
documents liés aux commandes.

## Mise à niveau depuis une ancienne version

Conservez votre fichier `data\commandes_cahpp.sqlite3` et le dossier
`documents` s'il existe, puis copiez-les dans le nouveau dossier portable.
L'application met automatiquement la base à niveau au premier démarrage.

## Limitation du prototype

L'exécutable Windows doit être compilé sur Windows : PyInstaller ne permet pas
de produire de manière fiable un `.exe` Windows depuis Linux. Le script
`build_windows.bat` automatise entièrement cette compilation. L'application
obtenue fonctionne ensuite sans Python et sans connexion Internet.
