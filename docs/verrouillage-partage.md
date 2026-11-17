# Verrouillage du partage — protocole 2, développement

Le partage reste le support de collaboration des PC. Aucun accès au relais
mobile n’est nécessaire pour réserver ou publier une commande.

Chaque ressource possède une sentinelle permanente `.guard`. Horizon verrouille
son premier octet avec `msvcrt.locking` sous Windows ou `fcntl.lockf` sous Linux.
La réservation utilisateur reste un fichier `.lock` à durée limitée ; sa
création, son renouvellement, sa reprise et sa suppression utilisent tous la
sentinelle. La publication vérifie le propriétaire **dans cette même section
critique et conserve l’exclusion jusqu’à la fin**. La comparaison des révisions
reste obligatoire. Une expiration ou une avance d’horloge peut faire perdre une
réservation, mais ne permet plus à son ancien détenteur d’écrire après reprise.

Les sentinelles ne sont jamais remplacées ou supprimées par Horizon. Leur
présence n’indique pas une réservation active. Ne pas les nettoyer à la main
pendant l’utilisation du partage. Un arrêt du processus libère le verrou natif.
Un refus du système de verrouiller interdit l’écriture ; aucun repli sur les
anciens verrous de présence n’est prévu.

Le renouvellement utilise un worker réservé, sans prendre le verrou des travaux
de synchronisation. Un renouvellement différé par une publication en cours est
reporté, car cette publication possède déjà l’exclusion native.

## Migration d’un partage existant

Cette migration est manuelle. Le simple lancement d’un exécutable de
développement ne convertit pas un partage au format 1.

1. Sauvegarder les profils PC et le dossier partagé. Installer la même nouvelle
   version sur **tous** les postes ; fermer tous les anciens exécutables.
2. Attendre l’expiration des anciennes réservations encore présentes.
3. Dans Paramètres → Collaboration, choisir **Mettre à niveau le partage…**.
   L’identité, les commandes, les documents et les catalogues sont conservés.
   Le manifeste original est copié dans `espace-collaboratif.format-1.json`.
4. Enregistrer les paramètres puis reconnecter les autres postes.

Un ancien client refuse le manifeste au format 2 lors de sa connexion. Un
ancien exécutable **déjà ouvert** ignore cependant le nouveau mécanisme : sa
fermeture avant la migration est indispensable. Ne pas restaurer le seul ancien
manifeste pendant que des postes sont connectés ; revenir en arrière exige un
arrêt coordonné et une restauration contrôlée du partage et des profils.

## Vérifier le vrai partage réseau

Les tests automatisés lancent des processus indépendants sous Windows et Linux.
Ils vérifient l’exclusion, l’arrêt forcé, le renouvellement, la reprise, le refus
d’une publication périmée et les erreurs de verrouillage. Ils ne reproduisent
pas les options de montage ou le comportement de votre serveur SMB/NFS.

Avant déploiement, utiliser **le même dossier réseau sur deux postes** :

1. Poste A : Paramètres → Collaboration → **Test à deux postes : réserver
   (30 s)**. Attendre le message « Verrou de test détenu ».
2. Pendant ces 30 secondes, poste B : **Test à deux postes : vérifier**.
   Le résultat attendu est « Exclusion observée ». Si le résultat indique
   « Aucune réservation détectée », ne pas migrer ni utiliser cette version sur
   ce partage tant que la cause n’est pas identifiée.
3. Après libération, vérifier que B peut réserver, puis inverser A et B.
4. Dans un espace de test, interrompre le réseau et fermer un poste pendant
   une réservation ; vérifier que les modifications locales restent conservées
   et que la reprise ne permet aucune publication par l’ancien détenteur.

Ce test touche seulement `verrous/.verification.guard`, jamais les commandes.
Le succès de la sonde confirme une exclusion à cet instant ; il ne certifie pas
à lui seul tous les scénarios de coupure/reconnexion du serveur de fichiers.

Références des primitives : [verrouillage Windows](https://learn.microsoft.com/en-us/windows/win32/fileio/locking-and-unlocking-byte-ranges-in-files),
[verrous fcntl Linux et limites sur les systèmes réseau](https://man7.org/linux/man-pages/man2/fcntl_locking.2.html).

## Diagnostic

Le rapport indique le numéro de protocole du partage. Les erreurs de lecture,
de renouvellement ou de publication sont journalisées sans contenu métier.
Les dates d’expiration restent des indications de bail, pas une preuve
d’exclusion du système de fichiers.
