# Historique des versions

## 1.4.2

- journal local rotatif (4 fichiers de 1 Mio maximum) pour le démarrage,
  la recherche, les erreurs d'interface, de workers, de PDF et de synchronisation ;
- journalisation des types d'erreurs, codes système et piles techniques sans
  enregistrer les recherches saisies, les données de commande ni les messages
  bruts d'exception ;
- rapport de diagnostic enrichi avec les événements récents, l'architecture
  du processus et les versions SQLite et Tk ;
- nettoyage des fichiers temporaires après échec d'une écriture JSON atomique ;
- retrait des verrous perdus de la liste des verrous utilisables ;
- tests de panne de publication, reprise, JSON endommagé et perte de verrou ;
- tests du journal, de sa rotation et du fonctionnement sans droit d'écriture ;
- test graphique isolé : construction et visite des neuf pages et recherche ;
- workflow GitHub Actions Windows/Linux : tests, Ruff, compilation Python et
  vérification PyInstaller sur Windows ;
- conservation du schéma SQLite 14.

## 1.4.1

- suppression autorisée dans l'historique pour les commandes **Brouillon**,
  **Générée** et **E-mail préparé**, tant qu'elles n'ont pas été marquées envoyées ;
- protection conservée si un envoi, une confirmation, une réception ou une
  facturation est enregistré, même si le statut affiché est incohérent ;
- confirmation explicite avant suppression et journal de suppression conservé ;
- propagation de la suppression aux autres postes par le mécanisme collaboratif ;
- nettoyage des pièces jointes locales et du dossier de préparation d'e-mail ;
- conservation des PDF exportés séparément ; rappel de retirer manuellement
  tout brouillon déjà ouvert dans la messagerie ;
- vérification atomique de l'éligibilité avant suppression ;
- tests de suppression après génération/préparation d'e-mail, synchronisation
  et refus de suppression des commandes envoyées ou suivies.

## 1.4.0

- recherche du catalogue déplacée hors du thread graphique afin d'éviter les
  gels de l'interface sur les postes plus lents ;
- worker unique conservant seulement la saisie la plus récente et annulant les
  recherches devenues obsolètes ;
- vérification automatique de la cohérence entre les articles et l'index FTS5 ;
- reconstruction automatique d'un index incomplet, absent ou endommagé ;
- suppression du basculement silencieux vers une recherche intégrale coûteuse ;
- mode de secours limité dans le temps lorsque FTS5 reste indisponible ;
- délai de saisie porté à 400 ms et recherche automatique à partir de deux
  caractères ;
- affichage progressif par lots de 25 lignes, avec 100 résultats initiaux et
  bouton **Afficher 100 de plus** ;
- enrichissement du rapport de diagnostic avec le nombre d'articles indexés,
  les entrées manquantes et les entrées orphelines ;
- ajout de tests de régression sur l'auto-réparation et les frappes rapides.

## 1.3.3

- correction de la conversion des points en virgules dans les coordonnées des
  fournisseurs ;
- format français limité aux seuls champs numériques **Minimum HT** et
  **Franco HT** ;
- réparation automatique et prudente des adresses e-mail, sites web, numéros
  de téléphone et coordonnées de contact déjà touchés par le défaut ;
- normalisation également appliquée aux données fournisseurs reçues par la
  synchronisation collaborative ;
- conservation des points dans les références, désignations, détails de
  conditionnement et notes lors de la modification d'un article ;
- migration automatique du schéma SQLite de la version 13 à 14.

## 1.3.2

- remplacement du séparateur classique du tableau de bord par le composant
  `ttk` compatible avec l'environnement Windows de compilation ;
- correction du blocage au démarrage provoqué par une option graphique non
  reconnue dans la première archive 1.3.1 ;
- conservation des tableaux redimensionnables et de leurs ascenseurs.

## 1.3.1

- ouverture maximisée par défaut afin d'utiliser l'espace réellement
  disponible sur l'écran ;
- séparation redimensionnable entre les tableaux des livraisons et des
  alertes ;
- ajout d'un ascenseur vertical indépendant sur chacun de ces tableaux ;
- conservation de l'état de sauvegarde et des boutons d'action en bas de la
  vue d'ensemble.

## 1.3.0

- alertes configurables lorsqu'une commande reste sans confirmation ou dépasse
  son échéance de livraison ;
- affichage des alertes sur le tableau de bord avec accès direct à la commande ;
- page **À recommander** calculant les échéances à partir des intervalles réels ;
- recommandation sélective de certains articles d'une ancienne commande ;
- détection d'une commande probablement créée en double dans les sept jours ;
- filtres personnalisés enregistrables dans l'historique ;
- délais moyens de confirmation et de livraison par fournisseur ;
- comparaison du dernier prix commandé avec le prix actuel du catalogue ;
- export Excel multi-feuilles des statistiques ;
- notes internes et référence de remplacement configurables sur un article ;
- ajout d'un service ou d'une unité destinataire sur la commande et son PDF ;
- lancement direct d'un installateur trouvé dans le dossier partagé, puis
  fermeture propre de l'application ;
- migration automatique du schéma SQLite de la version 12 à 13.

## 1.2.0

- ajout du statut **Confirmée** et d'une date de livraison prévisionnelle ;
- ajout des statuts **Partiellement livrée**, **Livrée** et **Facturée** ;
- saisie de plusieurs réceptions pour une même commande, avec date, numéro de
  bon de livraison, utilisateur et note ;
- réception article par article avec contrôle des quantités et calcul immédiat
  des reliquats ;
- correction ou suppression d'une réception avec recalcul automatique ;
- ajout de notes internes horodatées et partagées entre les utilisateurs ;
- synchronisation des réceptions, reliquats, confirmations, factures et notes ;
- enrichissement du tableau de bord avec l'état et le nombre d'unités restant à
  recevoir ;
- migration automatique du schéma SQLite de la version 11 à 12.

## 1.1.0

- ajout d'un tableau de bord des commandes envoyées restant à livrer ;
- ajout des états de livraison **En attente** et **Livrée**, synchronisés entre
  les postes et consignés dans le journal de la commande ;
- ajout d'une page **Statistiques** avec sélection de période et analyses par
  fournisseur et produit ;
- ajout de l'archivage automatique configurable des commandes livrées ;
- maintien des archives dans la base et possibilité de les afficher dans
  l'historique ;
- ajout d'un rappel visuel de sauvegarde et de la date du dernier contrôle ;
- contrôle périodique de l'intégrité SQLite et entretien hebdomadaire léger ;
- détection des nouveaux installateurs placés dans le sous-dossier partagé
  `mises-a-jour` ;
- migration automatique et compatible du schéma SQLite de la version 10 à 11.

## 1.0.1

- correction de l'icône du raccourci Bureau lors d'une mise à jour ;
- utilisation explicite de `assets\\app_icon.ico` par les raccourcis du
  Bureau et du menu Démarrer ;
- recréation du raccourci Bureau existant pendant l'installation, même si la
  tâche optionnelle n'est plus cochée lors d'une mise à jour ;
- respect du choix des utilisateurs qui n'ont aucun raccourci Bureau.

## 1.0.0

- publication de la première version stable après validation de la RC5 ;
- ajout de l'icône officielle **colis + checklist**, assortie aux couleurs de
  l'application ;
- création d'un fichier ICO multirésolution pour Windows, de 16 à 256 pixels ;
- affichage de l'icône dans la barre de titre et les fenêtres de
  l'application ;
- intégration de l'icône à l'exécutable PyInstaller, aux raccourcis, à
  l'installeur et au programme de désinstallation ;
- conservation intégrale des fonctions et correctifs validés en RC5 ;
- passage de la version affichée et des métadonnées d'installation à 1.0.0.

## 1.0.0-rc5

- retour à une barre d'actions unique dans l'historique des commandes ;
- augmentation de la largeur initiale de l'application à 1 450 pixels et
  largeur minimale fixée à 1 420 pixels afin de conserver tous les boutons
  entièrement visibles ;
- centrage de la fenêtre de classement d'un document sur la fenêtre
  **Documents associés** ;
- maintien du centrage dans les limites de l'écran ;
- conservation de l'autocomplétion sans perte de focus et des autres
  corrections introduites en RC4c.

## 1.0.0-rc4c

- remplacement du menu déroulant natif ouvert pendant la recherche d'un
  fournisseur par une liste de suggestions intégrée qui ne prend pas le focus
  clavier ;
- saisie continue de plusieurs lettres sans devoir recliquer dans le champ ;
- navigation possible dans les suggestions avec les flèches, la touche Entrée
  ou la souris ;
- réorganisation des actions de l'historique sur deux lignes afin d'éviter les
  boutons tronqués avec la mise à l'échelle de Windows ;
- remplacement de **Regénérer le PDF** par
  **Régénérer la commande** ;
- remplacement de **Documents / bon de livraison** par
  **Documents associés** ;
- suppression du raccourci redondant **Ajouter un bon de livraison** dans la
  fenêtre des documents ; le type reste disponible avec
  **Ajouter un document…**.

## 1.0.0-rc4b

- remplacement du libellé **Générer le PDF** par
  **Générer la commande** ;
- ajustement automatique des largeurs de colonnes une fois la largeur réelle
  de la page connue ;
- nouvel ajustement lors du redimensionnement de la fenêtre, sans masquer les
  colonnes situées à droite ;
- application de ce comportement au catalogue, aux articles disponibles et au
  contenu de la nouvelle commande ;
- ouverture automatique de la liste des fournisseurs filtrés pendant la
  saisie, sans devoir cliquer sur la flèche du champ ;
- détection d'Inno Setup lorsqu'il est installé uniquement pour l'utilisateur
  dans `AppData\Local`, via WinGet, Scoop ou son entrée de registre.

## 1.0.0-rc4

- ajout de catégories explicites pour les documents liés : bon de livraison,
  confirmation de commande, facture, devis, avoir, correspondance et pièce
  jointe e-mail ;
- ajout d'un type personnalisé pour classer les autres documents ;
- modification après ajout du type d'un document et de son inclusion dans la
  préparation du mail, désormais deux propriétés indépendantes ;
- élargissement du sélecteur aux principaux formats bureautiques, images,
  messages enregistrés et archives ;
- tri ascendant ou descendant par clic sur les en-têtes du catalogue, de la
  liste d'articles disponibles et du contenu de la commande ;
- maintien du tri choisi après une recherche ou un rafraîchissement ;
- ajout d'un script créant un installeur Windows unique sans droit
  administrateur ;
- lors d'une mise à jour par l'installeur, remplacement limité à l'exécutable
  et à ses dépendances, sans effacer la base locale, les documents, le logo,
  les PDF ni les sauvegardes.

## 1.0.0-rc3

- ajout d'un délai de synchronisation automatique configurable de 15 secondes
  à 10 minutes, avec une minute par défaut ;
- ajout de l'option, activée par défaut, mettant la synchronisation automatique
  en pause lorsqu'une fiche contient des modifications non enregistrées ;
- détection des saisies en cours dans les paramètres de l'établissement et
  dans les fiches fournisseurs ;
- protection contre le rafraîchissement d'un formulaire modifié, y compris
  lorsqu'une synchronisation avait déjà commencé avant la saisie ;
- reprise et synchronisation immédiate après l'enregistrement ;
- avertissement avant d'abandonner une fiche fournisseur non enregistrée ;
- précision accrue des horodatages collaboratifs afin qu'une sauvegarde faite
  juste après une réception soit toujours considérée comme la plus récente ;
- suppression de toute mention du franco atteint ou non atteint dans le PDF ;
- conservation du contrôle du franco uniquement dans l'interface, avant
  l'enregistrement ou la génération de la commande.

## 1.0.0-rc2

- ajout de **Supprimer le brouillon** dans l'historique ;
- limitation stricte de la suppression aux commandes encore au statut
  **Brouillon**, avec confirmation explicite ;
- utilisation du verrou collaboratif avant suppression pour empêcher
  l'effacement d'un brouillon ouvert sur un autre poste ;
- propagation de la suppression aux autres installations grâce à un marqueur
  versionné, empêchant le brouillon de réapparaître après synchronisation ;
- suppression des lignes, pièces jointes, copies d'envoi, fichiers partagés et
  anciennes révisions du brouillon ;
- conservation du numéro consommé afin de garantir la stabilité de la
  numérotation et de l'historique technique ;
- passage du schéma de base en version 10 avec migration automatique.

## 1.0.0-rc1

- ajout d'un diagnostic accessible depuis **Paramètres > Collaboration** ;
- contrôle SQLite `quick_check`, version du schéma, mode de journalisation,
  disponibilité de la recherche et détection d'enregistrements orphelins ;
- contrôle en lecture/écriture du dossier partagé, du renommage atomique, de
  l'identifiant de l'espace et de l'intégrité du catalogue publié ;
- affichage du nombre de commandes locales en attente et du bilan du dernier
  échange dans les paramètres et la barre latérale ;
- recensement des verrous actifs ou expirés et des utilisateurs concernés ;
- export ou copie d'un rapport de dépannage ne contenant ni tarif, ni ligne de
  commande, ni contenu de document ;
- ajout d'une checklist de validation à deux postes avant promotion en V1.0.

## 0.9.0

- ajout d'un mode collaboratif sans serveur : chaque poste conserve sa base
  SQLite locale et échange uniquement des fichiers versionnés dans un dossier
  réseau partagé ;
- création d'un profil nominatif au premier lancement, modifiable dans les
  paramètres, sans notion de poste ou d'emplacement ;
- choix, test, ouverture et modification du dossier partagé depuis l'onglet
  **Collaboration** ;
- synchronisation automatique et manuelle des commandes, fournisseurs,
  favoris, corrections du catalogue, articles hors catalogue et paramètres
  communs ;
- publication versionnée des catalogues CAHPP avec contrôle d'intégrité SHA-256
  et proposition d'installation sur les autres postes ;
- numérotation commune des commandes afin d'éviter les doublons ;
- verrou temporaire d'une commande ou d'un article pendant sa modification ;
- consultation locale maintenue lorsque le partage est indisponible, avec
  indication **Hors ligne — cache local** ;
- copie locale des PDF et documents reçus pour préserver leur consultation
  hors connexion ;
- ajout du créateur et de l'état de synchronisation dans l'historique ;
- ajout d'un journal nominatif des actions de chaque commande ;
- conservation de révisions récentes des données d'équipe et des commandes
  dans le dossier partagé ;
- retrait de la base de développement lors de la compilation du dossier
  portable : chaque poste démarre désormais avec sa propre base locale.

## 0.8.1b

- suppression de la fenêtre explicative après **Préparer le mail** ;
- conservation de l'ouverture automatique du message et du dossier contenant
  les pièces à joindre.

## 0.8.1

- retrait de la colonne redondante « Date du BC » dans l'historique ; la date
  reste conservée dans la base, le PDF et le nom du fichier ;
- suppression automatique du dossier temporaire
  `envois/<numero de commande>` lorsque la commande est marquée comme envoyée ;
- conservation du PDF original et des documents liés lors de ce nettoyage.

## 0.8.0

- ajout des dates de création et de premier envoi dans l'historique des
  commandes ;
- conservation de la première date d'envoi lorsqu'une commande est marquée
  plusieurs fois comme envoyée ;
- corrections locales des articles CAHPP sans modifier les valeurs importées,
  avec possibilité de rétablir les valeurs du catalogue ;
- modification et archivage des références créées par l'utilisateur ;
- suppression du code CAHPP dans le tableau du bon de commande PDF ;
- affichage automatique de la version du logiciel dans la barre latérale ;
- préparation des e-mails rendue plus générique, avec prise en charge de Gmail,
  des URL de composition génériques et des liens `mailto:` ;
- aide intégrée recensant les expressions utilisables dans l'objet et le corps
  des e-mails, dont `{date}` et `{total_ttc}`.

## 0.7.0

- remplacement des fenêtres de confirmation après enregistrement par un retour
  visuel temporaire directement sur le bouton concerné ;
- confirmation non bloquante pour les paramètres, les fournisseurs, les
  brouillons, la génération ou régénération des PDF et les sauvegardes ;
- affichage permanent de la section active dans la navigation latérale avec
  fond renforcé, texte en gras et liseré coloré ;
- conservation des fenêtres uniquement pour les erreurs, avertissements,
  décisions importantes et bilans détaillés.

## 0.6.1

- correction de la fenêtre des documents liés : la barre d'actions reste
  visible avec la mise à l'échelle de Windows et la hauteur s'adapte désormais
  au contenu et à l'écran.

## 0.6.0

- préparation locale des messages dans Gmail avec destinataire, objet et corps
  configurables ;
- regroupement automatique du PDF et des pièces jointes dans un dossier d'envoi ;
- duplication d'une ancienne commande en nouveau brouillon ;
- recherche dans l'historique par numéro, fournisseur, note, référence, code CAHPP
  ou désignation ;
- rattachement de bons de livraison et d'autres documents aux commandes ;
- intégration des documents liés dans la sauvegarde complète ZIP ;
- alerte après import pour les changements de prix ou de conditionnement
  concernant des articles déjà commandés ;
- coordonnées fournisseur enrichies, minimum de commande et franco ;
- contrôle des nombres de cartons non entiers et des seuils avant enregistrement ;
- affichage enrichi du conditionnement et favoris proposés par fournisseur ;
- migration automatique des bases créées avec les versions précédentes.

## 0.4.0

- nouveau nom PDF : `BC-AAAA-MM-JJ_Fournisseur.pdf` ;
- incrément journalier par fournisseur à partir de la deuxième commande.

## 0.3.0

- recherche par saisie dans la liste des fournisseurs ;
- création d'une commande directement depuis un article du catalogue ;
- choix du nom et de la destination lors de chaque génération PDF ;
- dossier PDF par défaut configurable.

## 0.2.0

- ajout de la modification des brouillons depuis l'historique ;
- conservation du numéro et de la date lors de la réédition ;
- titre du PDF personnalisable ;
- texte du pied de page personnalisable et vide par défaut ;
- affichage du numéro de page désactivable.

## 0.1.0

- import et mise à jour du catalogue CAHPP ;
- recherche, favoris, commandes et fournisseurs ;
- génération PDF et base SQLite portable.
