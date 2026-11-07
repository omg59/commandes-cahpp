# Guide du mode collaboratif

## Architecture retenue

Chaque PC possède une installation locale et une base SQLite locale. Le dossier
réseau sert uniquement de boîte d'échange entre les postes.

Les postes échangent leurs commandes, documents et catalogues par ce dossier.
Chaque application continue à interroger sa propre base locale.

Il ne faut pas exécuter l'application depuis le partage et il ne faut pas y
copier `data\commandes_cahpp.sqlite3`. Cette séparation évite les lenteurs de la
base de catalogue et les risques liés à SQLite sur un lecteur réseau.

## Installation sur deux postes

1. Copier `CommandesCAHPP-portable` dans un dossier local du premier PC.
2. Copier une seconde installation dans un dossier local du deuxième PC.
3. Créer un dossier commun accessible en lecture et écriture, par exemple
   `S:\Commandes CAHPP` ou `\\serveur\service\Commandes CAHPP`.
4. Lancer l'application sur le premier PC et renseigner le nom de
   l'utilisateur.
5. Dans **Paramètres > Collaboration**, activer le mode, sélectionner le dossier
   partagé, utiliser **Tester l'accès**, puis **Enregistrer**.
6. Répéter l'opération sur le second PC avec le nom de sa collègue et exactement
   le même dossier partagé.
7. Cliquer sur **Synchroniser maintenant** sur les deux postes.

Le premier poste crée automatiquement la structure de l'espace collaboratif.
Le second la rejoint grâce à son identifiant unique.

## Catalogue CAHPP

Lorsqu'un nouveau tarif arrive :

1. un seul utilisateur ouvre **Mise à jour CAHPP** et importe le fichier Excel ;
2. après contrôle, l'application publie une copie versionnée sur le partage ;
3. l'autre poste détecte la nouvelle version et propose de l'installer ;
4. l'empreinte SHA-256 du fichier est vérifiée avant l'import ;
5. les corrections manuelles déjà partagées restent prioritaires sur les
   valeurs brutes du nouveau catalogue.

Les favoris, conditionnements corrigés et articles hors catalogue n'attendent
pas un nouvel import : ils sont synchronisés dans les données d'équipe.

### Évolutions mensuelles depuis la 1.6.0

Mettre **tous les postes en 1.6.0 ou supérieure** avant le premier import
d'évolutions mensuelles. Le nouveau catalogue partagé est volontairement refusé
par les anciens importeurs pour éviter de réactiver les références retirées.

Le poste qui importe un fichier mensuel conserve les articles absents, applique
les statuts explicites et publie un **catalogue complet reconstitué**. L'autre
poste peut ainsi recevoir directement la dernière version, même s'il a manqué
plusieurs mois ; un nouveau poste peut également partir de cet instantané.
Le fichier mensuel original est archivé avec la version publiée. Les empreintes
du fichier source et du catalogue reconstitué sont conservées séparément.

Les informations à vérifier voyagent dans ce catalogue. Une correction et sa
confirmation sont synchronisées par les données d'équipe ; une confirmation
ne vaut que pour l'évolution concernée. Un nouveau changement de conditionnement
peut donc remettre l'article en attente de vérification sur les deux postes.

Appliquer d'abord tout catalogue partagé en attente avant d'importer le mois
suivant. Le verrou de catalogue protège l'import et sa publication. Si un autre
poste a publié entre-temps, la publication est refusée au lieu d'écraser son
travail. Le remplacement d'évolutions locales non publiées demande confirmation.

Si l'import local réussit mais que le partage est interrompu, l'interface le
signale distinctement. Relancer l'import du **même fichier** pour réessayer la
publication : les changements ne sont pas appliqués deux fois. Le manifeste
courant n'est remplacé qu'après copie et vérification de l'ensemble publié.
Chaque nouveau fichier appliqué depuis l'interface bénéficie d'une sauvegarde
complète locale préalable, y compris lors d'une réception depuis le partage.

## Travail simultané

- Deux utilisateurs peuvent travailler sur deux commandes différentes.
- Lorsqu'un brouillon est ouvert en modification, un verrou porte le nom de
  l'utilisateur et reste actif tant que l'écran est ouvert.
- Si la collègue tente d'ouvrir le même brouillon, elle peut toujours le voir
  dans l'historique mais ne peut pas le modifier.
- Le même principe protège les corrections d'un article.
- Les verrous expirent automatiquement si un poste s'éteint brutalement.
- Les numéros de commande sont réservés dans une séquence commune.

Le bouton **Journal** de l'historique permet de voir qui a créé, modifié,
généré, envoyé ou documenté une commande.

## Synchronisation et mode hors ligne

La synchronisation s'exécute :

- au lancement ;
- selon le délai configuré dans les paramètres ;
- après une modification importante ;
- avec **Synchroniser maintenant**.

Les commandes, PDF et documents reçus sont conservés dans le cache local du
poste. Si le partage disparaît, l'état **Hors ligne — cache local** apparaît :

- le catalogue et l'historique restent consultables ;
- les PDF et documents déjà synchronisés restent ouvrables ;
- les opérations nécessitant un verrou partagé sont bloquées pour éviter deux
  versions concurrentes ;
- la synchronisation reprend lorsque le partage redevient accessible.

Une commande enregistrée localement au moment précis d'une coupure porte l'état
**À synchroniser**. Elle sera publiée lors de la prochaine synchronisation.

## Contenu du dossier partagé

L'application gère elle-même ces éléments :

- `commandes` : état courant, documents et révisions des commandes ;
- `catalogues` : versions Excel publiées et manifestes d'intégrité ;
- `equipe` : fournisseurs, favoris, corrections, produits locaux et paramètres
  communs ;
- `verrous` : petits fichiers temporaires de coordination ;
- `mises-a-jour` : installateurs partagés déclenchant la notification de mise à jour ;
- `espace-collaboratif.json` : identité technique de l'espace.

Il ne faut pas renommer ou modifier ces fichiers manuellement. Une suppression
accidentelle peut être restaurée depuis la sauvegarde du dossier réseau.

## Sauvegardes conseillées

- Utiliser régulièrement **Paramètres > Sauvegarde** sur au moins un poste.
- Inclure le dossier partagé dans la sauvegarde habituelle du service si elle
  existe.
- Fermer l'application avant de déplacer une installation locale.
- Ne jamais fusionner manuellement deux fichiers SQLite.

## Changer le dossier partagé

Dans **Paramètres > Collaboration**, choisir le nouvel emplacement, tester
l'accès puis enregistrer. Pour conserver l'historique commun, copier auparavant
l'intégralité de l'ancien dossier partagé vers le nouveau lorsque les deux
applications sont fermées.

## Supprimer une commande non envoyée

Dans **Historique**, sélectionner une commande puis **Supprimer**. Une commande
au statut **Brouillon**, **Générée** ou **E-mail préparé** peut être supprimée tant
qu'aucun envoi ni suivi n'est enregistré. La suppression se propage aux autres
postes et une trace technique est conservée pour éviter sa réapparition.

Les PDF exportés séparément restent sur le disque. Un brouillon déjà ouvert
dans la messagerie doit être supprimé manuellement. L'application ne peut pas
détecter un envoi effectué en dehors de son suivi : marquer la commande envoyée
dès l'envoi réel au fournisseur.
