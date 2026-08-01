# Checklist de validation de la V1.1.0

## Migration

- [ ] L'installation par-dessus la V1.0.1 conserve la base et les documents.
- [ ] L'application affiche **Version 1.1.0**.
- [ ] Le diagnostic indique **Schéma : 11** et **Intégrité : OK**.

## Livraison

- [ ] Une commande marquée envoyée apparaît dans les livraisons en attente.
- [ ] Elle est visible sur le tableau de bord des deux postes après synchro.
- [ ] **Marquer livrée** la retire du tableau des attentes.
- [ ] **Remettre en attente** la fait réapparaître.
- [ ] Les actions figurent dans le journal de la commande.

## Statistiques

- [ ] La période **Cette année** affiche les commandes envoyées attendues.
- [ ] Les totaux HT et TTC correspondent à l'historique.
- [ ] Les tableaux fournisseur et produit peuvent être triés.
- [ ] Une période personnalisée accepte le format `AAAA-MM-JJ`.

## Archivage et sauvegarde

- [ ] L'archivage manuel masque les anciennes commandes livrées.
- [ ] **Inclure les archives** permet de les consulter à nouveau.
- [ ] L'archivage est synchronisé entre les deux postes.
- [ ] Une sauvegarde complète met à jour la date affichée.
- [ ] Le contrôle d'intégrité affiche un résultat positif.

## Mise à jour partagée

- [ ] Le dossier partagé contient un sous-dossier `mises-a-jour`.
- [ ] Un fichier `CommandesCAHPP-Setup-1.2.0.exe` y déclenche une notification.
- [ ] Refuser la notification ne la réaffiche pas à chaque synchronisation.
