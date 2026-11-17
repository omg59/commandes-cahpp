# Isolation des espaces mobiles — développement

Ce lot associe Horizon PC **3.0.1a3**, Horizon Server **0.5.0-dev1** et Horizon
Mobile **0.6.0-dev1**. Il reste sur les branches `dev` et ne remplace pas les
versions distribuées.

Le relais reste mono-établissement. Son identifiant d’instance est conservé dans
son volume SQLite. Le PC lui transmet l’identifiant stable du partage
collaboratif, commun aux collègues. Un autre partage ne peut pas utiliser le
même relais. Pour une autre base, utiliser un relais et un volume distincts.

La même URL HTTPS peut désigner une nouvelle instance après remplacement d’un
volume ; son identifiant change alors. Android crée un autre espace local,
même si l’adresse et le catalogue sont identiques. Paniers, favoris, cache du
catalogue, fournisseurs, demandes immuables, réceptions, photos, commandes
consultées, brouillons masqués et documents téléchargés restent séparés.

## Passage depuis les versions actuelles

1. Sauvegarder les profils PC, le partage et le volume du relais. Tester ce lot
   dans un espace isolé avant d’envisager la production.
2. Mettre à jour tous les PC et suivre la [migration du protocole de
   verrouillage](verrouillage-partage.md). Garder le relais et Android actuels
   tant que le lot complet n’est pas prêt.
3. Mettre à jour le relais **en conservant son volume**. Le démarrage ajoute son
   identifiant d’instance ; il ne choisit pas automatiquement une base.
4. Sur le bon PC, Paramètres → Android → **Rattacher le relais à cette base…**.
   Un relais vide est lié directement. S’il contient déjà des commandes ou des
   demandes, vérifier leur origine puis confirmer leur rattachement. Le refus
   de confirmation laisse les données et l’identité inchangées.
5. Installer la nouvelle application Android, puis enregistrer et tester la
   connexion dans ses réglages. L’espace isolé s’ouvre ; les versions mobiles
   antérieures ne peuvent plus envoyer de données au relais lié.

Avant le rattachement, le relais maintient la compatibilité avec les clients
historiques. **Après rattachement**, les anciennes versions PC/mobile sont
refusées sur les routes métier : elles ne transmettent pas les deux identités.
Les contrôles de compatibilité CI couvrent le mode historique non rattaché
pour le PC stable, et le protocole isolé pour le PC candidat.

## Données déjà présentes sur Android

Les données antérieures à cette version restent dans un espace local nommé
« anciennes données ». Elles ne sont pas associées automatiquement à une base
sur la seule foi de son URL. On peut les consulter depuis les réglages.

L’action **Copier l’ancien panier et les favoris…** est explicite. Elle exige
un panier cible vide, vérifie les articles dans le catalogue courant, actualise
les tarifs et retire le lien éventuel à un ancien brouillon. La source reste
intacte. Vérifier auparavant qu’aucune commande correspondante n’a déjà été
créée sur le PC.

Les anciennes demandes en attente et les réceptions ne sont **jamais envoyées
automatiquement dans un nouvel espace**. Leur présence sur le téléphone ne
prouve pas qu’elles n’ont pas déjà été traitées sur l’ancien PC : contrôler le
suivi avant toute recréation manuelle. Les espaces déjà identifiés restent
également accessibles depuis les réglages, avec leurs données propres.

Un worker Android commencé dans un espace conserve ses propres stores et son
identité réseau. Un changement d’écran ou d’espace ne peut pas déplacer son
résultat vers le nouvel espace. Le relais vérifie les identités sous transaction
SQLite avant lecture ou mutation ; une vérification préalable seule ne suffit
donc pas à autoriser l’envoi.

Les réponses Android sont limitées à 17 Mio et les messages d’erreur à 4 Kio.
La pagination et les quotas feront l’objet du lot de capacité H06.
