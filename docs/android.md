# Android et relais de synchronisation

Horizon PC 3.0.0 fonctionne avec **horizon-server 0.4.0** et **Horizon Mobile 0.4.0**.
Ces composants ont leur propre version et leur propre cycle de publication.
Le PC seul fonctionne sans relais. Pour Android, un relais suffit pour tous les
utilisateurs d’un établissement, même hors du réseau local des postes fixes.

## Installer et connecter

Déployer [horizon-server](https://github.com/omg59/horizon-server) avec Docker / Portainer,
puis publier son adresse HTTPS via le reverse proxy. Le port hôte peut être 8081
si 8080 est déjà utilisé ; conserver le port interne indiqué dans le guide serveur.
Les clés PC et mobile sont distinctes. Ne pas les publier dans un rapport ou une capture.

Dans **Paramètres → Collaboration** sur PC, configurer et enregistrer le dossier
partagé de l’équipe. Dans **Paramètres → Android**, saisir l’adresse HTTPS du
relais et la **clé PC** (`HORIZON_PC_TOKEN`), puis **Enregistrer la connexion**.
Sur [Horizon Mobile](https://github.com/omg59/horizon-mobile), saisir la même
adresse, la **clé mobile** et le nom de la personne qui utilise le téléphone.

La mémorisation de la clé PC est facultative. L’option **Mémoriser la clé dans
le fichier local de ce profil** la conserve en clair dans `interface.ini` ;
sans cette option, elle reste disponible uniquement pendant la session.
`HORIZON_RELAY_URL` et `HORIZON_PC_TOKEN` peuvent aussi préremplir la connexion.
La connexion est directe par défaut. Cocher **Utiliser le proxy système pour
joindre le relais** si le réseau l’impose. La vérification HTTPS reste active.

## Synchronisation automatique

Activer **Synchroniser automatiquement avec Android**, choisir l’intervalle
(60 secondes par défaut), puis enregistrer. Horizon doit rester ouvert sur un
poste pour traiter les demandes. Le cycle attend la fin des saisies et imports,
puis reprend après les erreurs réseau. Le bouton de synchronisation manuelle
reste disponible. Les erreurs et l’avancement figurent dans cet onglet et dans
les diagnostics.

Le catalogue est transmis par blocs compressés lorsque le relais le permet.
Le premier envoi d’un grand catalogue peut prendre plusieurs cycles. Les blocs
reçus sont conservés après une interruption. Une génération déjà publiée est
réutilisée ; le transfert reprend au lieu de recommencer intégralement.
Le catalogue publié reste consultable sur le relais lorsque les PC sont fermés.

## Travail à plusieurs

Chaque téléphone transmet un **nom déclaré** qui accompagne les commandes,
notes et réceptions dans l’historique. La clé mobile donne accès aux données de
l’équipe : ces noms ne constituent pas des comptes avec des droits individuels.
Il n’est pas nécessaire de déployer un relais par utilisateur.

Les commandes créées ou modifiées sur mobile sont vérifiées par le PC avec les
prix et conditionnements courants. Le PC attribue le numéro et génère le PDF.
Les paniers peuvent être enregistrés comme **Brouillons**, synchronisés puis
repris sur PC ou mobile sans changer leur numéro. Les révisions et verrous
protègent les modifications effectuées simultanément sur un autre poste.

Les commandes envoyées avec un reliquat peuvent être réceptionnées sur le
téléphone. Plusieurs photos sont réunies en un bon de livraison PDF, dans
l’ordre choisi. Sans photo, une confirmation permet d’envoyer la réception,
sans créer de document artificiel. Les réceptions partielles, documents et
notes sont intégrés au PC puis aux autres postes par le dossier partagé.

La liste des demandes et synchronisations se trouve dans les réglages mobiles,
pour suivre et nettoyer l’historique de diagnostic. Le nettoyage confirmé
retire les demandes traitées ou refusées, y compris les paniers refusés non repris.
Reprendre ces paniers avant de vider la liste. Les demandes en attente et les
commandes partagées sont conservées.

## Mise à jour et diagnostic

Mettre à jour le relais, les PC puis les téléphones. Utiliser la même version PC
sur les postes d’un partage. Pour un incident, exporter le diagnostic PC et
consulter l’état de synchronisation mobile ; il n’est pas nécessaire de partager
les clés, le contenu des commandes ou les photos pour identifier un échec réseau.
