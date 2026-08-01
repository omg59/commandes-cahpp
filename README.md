# Commandes CAHPP

Application Windows locale pour importer un catalogue tarifaire CAHPP, retrouver
rapidement les articles, préparer des commandes fournisseurs et générer des bons
de commande PDF. Le mode collaboratif optionnel permet à plusieurs postes de
travailler ensemble à travers un simple dossier partagé, sans serveur.

**Version stable actuelle : 1.3.0**

## Principes

- application, catalogue et base SQLite conservés localement sur chaque poste ;
- aucun serveur, compte en ligne ou droit administrateur nécessaire ;
- synchronisation optionnelle par fichiers versionnés dans un dossier partagé ;
- import d'un nouveau fichier Excel CAHPP avec comparaison de la version
  précédente ;
- conservation des tarifs historiques et des lignes de commandes déjà créées ;
- recherche par fournisseur, code CAHPP, référence ou désignation ;
- tri des tableaux par clic sur les titres de colonnes ;
- favoris et quantités habituelles ;
- duplication des commandes récurrentes ;
- recherche dans tout l'historique, y compris les références et désignations ;
- suivi des commandes envoyées restant à livrer ;
- confirmations fournisseur et dates de livraison prévues ;
- réceptions partielles avec plusieurs bons de livraison et calcul des reliquats ;
- suivi de la facturation et notes internes partagées sur chaque commande ;
- statistiques par période, fournisseur et produit ;
- archivage configurable des anciennes commandes livrées ;
- rappel de sauvegarde et contrôle périodique de l'intégrité SQLite ;
- notification lorsqu'un nouvel installeur est déposé dans le partage ;
- lancement direct de l'installateur partagé avec fermeture propre de l'application ;
- alertes configurables sur les confirmations manquantes et livraisons en retard ;
- suggestions d'articles à recommander selon leur rythme historique ;
- filtres d'historique enregistrés et recommandation sélective d'articles ;
- indicateurs de délai fournisseur, comparaison des prix et export Excel ;
- notes internes et références de remplacement dans le catalogue ;
- service ou unité destinataire mémorisé sur la commande et imprimé sur le PDF ;
- suivi des changements de prix et de conditionnement des articles commandés ;
- rattachement des bons de livraison et autres documents ;
- préparation des e-mails sans mot de passe ni droit administrateur ;
- sauvegarde complète de la base et des documents liés ;
- bon PDF commun à tous les fournisseurs.

## Collaboration sans serveur

Le mode collaboratif ne place jamais la base SQLite sur le réseau. Chaque utilisateur
installe son propre dossier `CommandesCAHPP-portable` sur son PC. Seul le dossier
choisi dans **Paramètres > Collaboration** doit être commun aux utilisateurs.

Ce mode synchronise :

- les commandes, leur statut, leur PDF et leurs documents liés ;
- les fournisseurs, favoris et quantités habituelles ;
- les corrections manuelles des articles CAHPP ;
- les articles hors catalogue, y compris leur modification ou archivage ;
- les paramètres communs de l'établissement, du PDF et des modèles d'e-mail ;
- la version du catalogue CAHPP publiée par un utilisateur.

Un numéro de commande est réservé de manière commune. Une commande ou un article
en cours de modification est temporairement verrouillé au nom de l'utilisateur.
Les autres commandes restent utilisables en parallèle.

La synchronisation s'effectue au démarrage, selon le délai choisi, après les
actions importantes et à la demande. Le délai automatique est configurable
dans **Paramètres > Collaboration**, de 15 secondes à 10 minutes.

Par défaut, la synchronisation automatique se met en pause dès que la fiche
établissement ou une fiche fournisseur contient une saisie non enregistrée.
Le formulaire affiché est également protégé contre un rafraîchissement déjà en
cours. L'enregistrement déclenche ensuite immédiatement la synchronisation.

Les PDF et documents reçus sont aussi mis en cache localement. Si le réseau
disparaît, l'historique reste consultable ; les modifications nécessitant un
verrou sont bloquées jusqu'au retour du partage afin d'éviter les conflits.

## Confort d'utilisation

La section actuellement ouverte reste mise en évidence dans la barre latérale.
Le numéro de version du logiciel est affiché en bas de cette barre.
Après un enregistrement réussi, le bouton concerné passe temporairement au vert
et confirme l'action sans ouvrir de fenêtre supplémentaire.

Les fenêtres restent utilisées lorsqu'une décision, une erreur, un
avertissement ou un bilan détaillé nécessite l'attention de l'utilisateur.

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

Le résultat se trouve dans `dist\CommandesCAHPP-portable`. Copiez séparément ce
dossier sur chaque poste. Les données de chaque utilisateur restent dans
`data\commandes_cahpp.sqlite3`, à côté de son application. Le script de
compilation ne copie aucune base de développement.

## Création de l'installeur Windows

Pour obtenir un seul fichier `.exe` d'installation et de mise à jour, installez
une fois [Inno Setup 6](https://jrsoftware.org/isinfo.php) sur le PC Windows qui
sert à compiler, puis lancez :

```bat
build_installer_windows.bat
```

Le fichier obtenu se trouve dans :

```text
dist-installer\CommandesCAHPP-Setup-1.3.0.exe
```

Le script détecte Inno Setup dans le `PATH`, dans `Program Files`, dans
`%LOCALAPPDATA%\Programs\Inno Setup 6`, ainsi que dans les emplacements WinGet,
Scoop et les entrées de registre habituelles. Une installation limitée au
compte utilisateur est donc prise en charge.

L'installeur fonctionne sans droit administrateur. Il remplace uniquement
`CommandesCAHPP.exe` et `_internal` ; il conserve la base `data`, les documents,
le logo et les autres fichiers utilisateur. Lors de la première mise à jour
d'une installation portable existante, choisissez son dossier actuel. Les
mises à jour suivantes réutiliseront automatiquement ce dossier.

Il ne s'agit pas d'une mise à jour téléchargée depuis Internet : l'EXE est
placé volontairement dans le dossier partagé par l'utilisateur qui prépare la
version.

En mode collaboratif, le sous-dossier `mises-a-jour` est créé automatiquement
dans l'espace partagé. Un installeur nommé
`CommandesCAHPP-Setup-X.Y.Z.exe` qui y est déposé déclenche une notification
sur les postes utilisant une version antérieure. L'utilisateur peut lancer
l'installation directement ; l'application ferme alors proprement ses verrous
et laisse l'installateur remplacer uniquement les fichiers du programme.

## Première utilisation

1. Au premier lancement, renseigner le nom qui apparaîtra dans l'historique.
2. Si plusieurs postes sont utilisés, choisir le même dossier dans
   **Paramètres > Collaboration** sur chacun d'eux.
3. Ouvrir **Paramètres** et renseigner l'établissement.
4. Sur un seul poste, ouvrir **Mise à jour CAHPP** et sélectionner le fichier
   Excel du catalogue à utiliser. Il sera proposé aux autres postes.
5. Configurer les fournisseurs utilisés : numéro client, adresse e-mail et
   montant du franco.
6. Marquer les articles habituels comme favoris.
7. Préparer une commande et générer le PDF.

Le guide détaillé [GUIDE_COLLABORATION_0.9.0.md](GUIDE_COLLABORATION_0.9.0.md)
explique l'installation à deux postes et les comportements en cas de coupure.

## Diagnostic et assistance

Le bouton **Diagnostic** de l'onglet **Collaboration** contrôle :

- l'intégrité de la base SQLite locale ;
- la version du schéma et le fonctionnement de la recherche ;
- les commandes restant à synchroniser ;
- l'accès en lecture et en écriture au dossier partagé ;
- la cohérence de l'identifiant collaboratif ;
- la présence et l'intégrité du catalogue partagé ;
- les verrous collaboratifs encore actifs ou expirés.

Le rapport peut être copié ou enregistré au format texte. Il contient les
chemins techniques, la version et le nom du profil, mais aucun tarif, article,
contenu de commande ou document. Il peut donc être transmis pour analyser un
problème sans exposer les données métier.

Avant de considérer la version comme validée, suivre
[CHECKLIST_VALIDATION_V1.md](CHECKLIST_VALIDATION_V1.md) sur les deux postes.

La liste des fournisseurs de l'écran **Nouvelle commande** est filtrée pendant
la saisie du nom. Depuis **Catalogue**, sélectionner un article puis cliquer sur
**Commander cet article** pour ouvrir directement une commande avec le bon
fournisseur.

Les favoris du fournisseur sont affichés en premier dans la préparation d'une
commande. En l'absence de recherche, la liste est limitée aux favoris s'il en
existe.

## Corriger et gérer les articles

Dans **Catalogue**, le bouton **Modifier l'article** permet de corriger la
référence fournisseur, la désignation, le conditionnement, son détail, le prix
et la TVA.

Pour un article CAHPP, la correction est enregistrée séparément de la valeur
importée. Elle reste active après les imports suivants. La mention `CAHPP ✎`
signale une correction et **Rétablir CAHPP** supprime les corrections locales.

Les références créées avec **Article hors catalogue** sont identifiées par
`Local`. Elles peuvent être modifiées ou supprimées. La suppression les archive
sans modifier les anciennes commandes.

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
Le PDF contient uniquement la référence utile au fournisseur ; le code interne
CAHPP n'y est pas affiché.

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

Un brouillon devenu inutile peut être retiré avec **Supprimer le brouillon**.
L'application demande une confirmation et, en mode collaboratif, vérifie
d'abord que le brouillon n'est pas ouvert sur un autre poste. La suppression
est ensuite synchronisée et le brouillon ne réapparaît pas lorsqu'un poste
resté hors ligne se reconnecte. Les commandes générées, préparées ou envoyées
ne sont pas supprimables afin de préserver la traçabilité.

L'historique affiche la date de création, le créateur, l'état de
synchronisation et la première date d'envoi. Cette dernière est renseignée avec
**Marquer envoyée**. La date propre au bon reste conservée dans la base et
utilisée dans le PDF et son nom de fichier. Le bouton **Journal** détaille les
actions nominatives de la commande.

## Préparer une commande par e-mail

Dans **Fournisseurs**, renseignez l'adresse e-mail de commande. L'adresse de
composition, l'objet et le message peuvent être modifiés dans **Paramètres**.
La liste des expressions disponibles y est affichée :

```text
{order_number} {date} {order_date} {supplier} {supplier_email}
{customer_number} {total_ht} {total_ttc}
{establishment_name} {establishment_subtitle}
```

`{date}` correspond à la date du bon au format `JJ/MM/AAAA`, tandis que
`{order_date}` conserve le format `AAAA-MM-JJ`.

Dans **Historique**, le bouton **Préparer le mail** :

1. ouvre un message avec le destinataire, l'objet et le texte préremplis ;
2. ouvre un dossier contenant le PDF et toutes les pièces marquées
   **Joint au mail** ;
3. permet de joindre l'ensemble par `Ctrl+A`, puis glisser-déposer.

Gmail reste configuré par défaut. Une URL de composition générique ou `mailto:`
peut également être utilisée. L'ajout final des pièces jointes reste manuel :
aucun identifiant ni mot de passe de messagerie n'est enregistré.

Lorsque la commande est marquée comme envoyée, son sous-dossier temporaire dans
`envois` est supprimé automatiquement. Le PDF original et les documents liés à
la commande sont conservés à leur emplacement habituel.

## Documents et bons de livraison

Dans **Historique**, sélectionnez une commande puis ouvrez
**Documents associés**. Les fichiers choisis sont copiés dans
`documents\<numero de commande>` à côté de l'application. En mode collaboratif,
une copie est publiée dans l'espace partagé puis mise en cache sur l'autre
poste. Ils restent ainsi liés à la commande même si le fichier original du
scanner est déplacé ou si le partage est temporairement indisponible.

**Ajouter un document…** permet de classer le fichier comme bon de livraison,
confirmation de commande, facture, devis, avoir, correspondance, pièce jointe
e-mail ou avec un type personnalisé. Les PDF, images, fichiers bureautiques,
messages `.eml`/`.msg`, textes et archives peuvent être conservés.

Le type du document et son inclusion au mail sont indépendants. Sélectionnez
une ligne puis cliquez sur **Type / mail…** pour modifier l'un ou l'autre après
l'ajout. Les bons de livraison ne sont pas joints au mail par défaut.

## Trier les articles

Dans **Catalogue** et **Nouvelle commande**, cliquez sur le titre d'une colonne
— référence, désignation, fournisseur, prix, conditionnement ou quantité — pour
trier le tableau. Un second clic inverse le sens du tri. La flèche `▲` ou `▼`
indique le classement actif, qui est conservé lors des recherches suivantes.

## Mise à jour des tarifs

Après l'import d'un catalogue, l'application signale les variations de prix ou
de conditionnement qui concernent des articles déjà commandés. Le détail reste
consultable depuis l'historique des imports. Les anciennes commandes conservent
toujours leurs valeurs d'origine.

En mode collaboratif, l'utilisateur qui reçoit le nouveau fichier l'importe une
seule fois. Le fichier est copié dans le dossier partagé avec sa version, son
empreinte SHA-256 et l'auteur de la publication. Les autres postes proposent
ensuite son installation. Les corrections manuelles sont conservées au-dessus
des nouvelles données CAHPP et continuent d'être synchronisées.

## Seuils et conditionnements

Les coordonnées, le minimum de commande et le franco se configurent dans
**Fournisseurs**. Avant l'enregistrement, l'application avertit si :

- le nombre de cartons d'une ligne n'est pas entier ;
- le minimum de commande n'est pas atteint ;
- le franco n'est pas atteint.

L'utilisateur peut confirmer et continuer si le fournisseur accepte une
exception. Ces vérifications sont strictement internes : le PDF envoyé au
fournisseur ne mentionne jamais si le franco est atteint ou non.

## Sauvegarde complète

Le bouton **Exporter une sauvegarde complète**, dans l'onglet **Sauvegarde**
des paramètres, crée une archive ZIP contenant la base SQLite et tous les
documents locaux, y compris les copies mises en cache. Le dossier partagé
conserve par ailleurs les dernières révisions des commandes et des données
d'équipe ; il ne remplace pas une sauvegarde régulière.

## Mise à niveau depuis une ancienne version

Avec l'installeur V1.0, fermez l'application puis lancez le nouvel EXE en
conservant le même dossier d'installation. La base et les documents ne sont pas
remplacés. Une sauvegarde complète préalable reste conseillée.

Pour une mise à niveau manuelle, conservez votre fichier
`data\commandes_cahpp.sqlite3` et le dossier `documents`, puis remplacez
uniquement `CommandesCAHPP.exe` et `_internal`. L'application met
automatiquement la base à niveau au premier démarrage.

Ne placez ni l'exécutable ni `data\commandes_cahpp.sqlite3` dans le dossier
réseau ; configurez uniquement ce dernier depuis l'application.

## Compilation Windows

L'exécutable Windows doit être compilé sur Windows : PyInstaller ne permet pas
de produire de manière fiable un `.exe` Windows depuis Linux. Le script
`build_windows.bat` automatise entièrement cette compilation. L'application
obtenue fonctionne ensuite sans Python et sans connexion Internet. Le mode
collaboratif suppose seulement que Windows donne accès en lecture/écriture au
dossier réseau configuré.
