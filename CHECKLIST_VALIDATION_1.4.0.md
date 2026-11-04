# Validation de Commandes CAHPP 1.4.0

## Compilation et démarrage

- Vérifier que `cahpp_app/__init__.py` indique `1.4.0`.
- Compiler avec `build_installer_windows.bat`.
- Vérifier la création de `CommandesCAHPP-Setup-1.4.0.exe`.
- Installer par-dessus la 1.3.3 et confirmer la conservation des données.

## Recherche catalogue

- Ouvrir **Catalogue** et saisir rapidement plusieurs caractères.
- Vérifier que l'interface reste utilisable pendant la recherche.
- Vérifier que seule la dernière saisie est affichée.
- Confirmer l'affichage initial de 100 résultats au maximum.
- Tester **Afficher 100 de plus** sur une recherche large.
- Vérifier le filtre fournisseur et **Favoris uniquement**.
- Vérifier la modification, le favori et la commande d'un article trouvé.

## Réparation et diagnostic

- Ouvrir **Paramètres > Diagnostic**.
- Vérifier `Recherche plein texte : OK`.
- Vérifier `Index de recherche : OK`.
- Comparer `Articles indexés` au nombre total d'articles.
- Confirmer l'absence d'entrées manquantes ou orphelines.

## Non-régression

- Créer puis reprendre un brouillon.
- Générer un PDF.
- Contrôler les coordonnées fournisseur avec des points.
- Effectuer une synchronisation sur les deux postes.
- Tester la notification d'une mise à jour partagée.
