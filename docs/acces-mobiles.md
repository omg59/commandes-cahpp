# Téléphones et clé PC — développement

Le relais est commun à l’établissement. Chaque téléphone dispose de sa propre clé.

## Associer un téléphone par QR code

Dans **Paramètres → Android → Gérer les téléphones autorisés**, choisissez
**Associer par QR code**. Horizon utilise le nom et l’identifiant du profil PC
actif. Le libellé du téléphone est facultatif et aide à le retrouver dans la liste.

Dans **Horizon Mobile → Réglages**, choisissez **Scanner le QR code du PC**.
Vérifiez le nom et l’adresse HTTPS avant de confirmer. Le réseau mobile peut
être utilisé. Si la connexion coupe, réessayez depuis le dialogue ouvert pour
reprendre la même association.

Le QR vaut cinq minutes et associe un seul téléphone. Fermer le dialogue PC
demande l’annulation d’un code inutilisé. Le téléphone crée sa clé et peut
la mémoriser avec Android Keystore. Pour deux appareils, générez deux codes.

Versions de test : PC 3.0.1a9, relais 0.5.0-dev6 et Android 0.6.0-dev7.

## Enregistrer les téléphones manuellement

Après rattachement du relais au bon partage, ouvrir Paramètres → Android →
**Gérer les téléphones autorisés…**. Renseigner le nom attribué aux opérations
et le libellé de l’appareil. Enregistrer, copier la clé affichée masquée et la
coller dans les réglages du téléphone concerné. La clé PC n’est jamais utilisée
sur le téléphone. Le relais ne conserve que l’empreinte des clés d’appareils.

Une nouvelle base relais vide exige immédiatement des clés individuelles. Pour
des données historiques adoptées, la clé commune reste provisoirement acceptée.
Terminer les demandes en cours, enregistrer les téléphones et vérifier leurs
connexions. Utiliser ensuite **Désactiver la clé Android commune…** : tant
qu’elle fonctionne, elle contourne la révocation individuelle.

Les noms transmis par le téléphone ne peuvent plus remplacer l’auteur lié à
sa clé sur le relais. Les anciennes demandes acceptées restent telles qu’elles
étaient : leur attribution historique n’est pas réécrite. Les clés donnent les
mêmes fonctions mobiles de consultation, création et réception ; il n’y a pas
de profils de droits différenciés ni de connexion SSO dans ce lot.

## Perte, exposition ou remplacement d’une clé

**Révoquer ce téléphone…** refuse ses futures requêtes sans couper les autres.
Les commandes et demandes déjà reçues restent disponibles pour traitement.
**Renouveler sa clé** invalide l’ancienne et conserve l’identité. Pour un appareil
révoqué, cette action le réautorise avec un nouveau secret ; l’ancienne clé
révoquée ne peut pas être réactivée. Copier la nouvelle clé sur le téléphone
après vérification de son origine.

La clé est générée sur le PC, conservée en mémoire le temps du dialogue et
copiable explicitement. Si un accusé réseau est perdu, la répétition de la même
opération réutilise son identifiant et son secret. Une fois le dialogue fermé,
le relais ne permet pas de relire la clé : la renouveler si nécessaire.

## Stockage de la clé PC

La case **Mémoriser la clé dans le coffre sécurisé du système** utilise Windows
Credential Locker, Secret Service ou KWallet lorsque ce service est disponible.
La dépendance keyring est limitée aux backends natifs sélectionnés explicitement ;
aucun backend fichier tiers ni stockage en clair n’est accepté.

Le fichier `interface.ini` ne contient qu’une référence opaque, propre au profil
et au relais. Une copie ou un déplacement du profil ne réutilise pas l’entrée de
coffre de l’ancien emplacement. Les sauvegardes métier contiennent la base et
les documents, jamais la clé du coffre.

Au premier lancement, une ancienne clé en clair est transférée vers le coffre
avec contrôle de relecture, puis supprimée des paramètres. Si le coffre est
indisponible ou refuse la mémorisation, la clé reste utilisable pour cette
session et un message l’indique. Il faudra la saisir de nouveau au prochain
lancement. Aucune copie en clair de remplacement n’est créée.

Décocher la mémorisation retire la référence et supprime l’entrée native lorsque
le coffre est accessible. Si son effacement ne peut pas être confirmé, le
message le précise et Horizon cesse de réutiliser cette référence. Les copies
de configurations antérieures à cette migration peuvent toujours contenir
l’ancienne clé : renouveler `HORIZON_PC_TOKEN` dans Portainer puis reconnecter
les PC pour rendre ces anciennes copies inutilisables.

Le diagnostic indique seulement le backend et l’état de mémorisation. Les clés
ne sont ni exportées dans le rapport, ni incluses dans les journaux.
