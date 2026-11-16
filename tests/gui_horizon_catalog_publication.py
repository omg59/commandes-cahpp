"""Publier depuis Qt un mois déjà importé avant l’activation du partage."""
from unittest.mock import patch

from tests.gui_horizon import wait


def main():
    from cahpp_app.horizon.bootstrap import configure

    profile, info = configure([])
    from PySide6.QtWidgets import QMessageBox
    from cahpp_app.database import Database
    from cahpp_app.catalog_importer import CatalogImporter, ImportOptions
    from cahpp_app.collaboration import CollaborationManager
    from cahpp_app.horizon.application import HorizonWindow, create_application
    from tests.test_workflow import create_catalog
    from tests.test_monthly_catalog import create_monthly, monthly_row

    app = create_application()
    database = Database(profile / "data/commandes_cahpp.sqlite3")
    base = profile / "base-octobre.xlsx"
    create_catalog(base, [{"Catalogue": "DM", "IDFournisseur": 11020, "NomFournisseur": "HARTMANN",
        "CodeCahpp": "DM001", "RéférenceArticle": "REF-DM001", "DésignationArticle": "ARTICLE",
        "PrixUnitaireCahpp": 1, "Conditionnement": 10, "Qml": 10, "TVA": 20}])
    CatalogImporter(database).import_file(base)
    other = Database(profile / "other.db")
    result = CatalogImporter(other).import_file(base)
    manager = CollaborationManager(other, "autre", "Autre poste", profile / "partage")
    manager.initialize_workspace()
    manager.publish_catalog(base, result)
    source = profile / "2026-11 EVO TARI.xlsx"
    create_monthly(source, [monthly_row(price=8)])
    CatalogImporter(database).import_file(source, options=ImportOptions(confirm_baseline=True))
    database.save_settings({"collaboration_enabled": "1", "shared_workspace_path": str(profile / "partage")})
    window = HorizonWindow(database, profile, info)
    window.show()
    with patch.object(QMessageBox, "warning") as errors, patch.object(QMessageBox, "information"):
        wait(app, lambda: not window.jobs.tasks)
        window.navigate("imports")
        wait(app, lambda: not window.jobs.tasks)
        assert window.imports.publish.isEnabled()
        assert not window.imports.shared.isEnabled()
        assert "n’a pas été publié" in window.imports.status.text()
        with patch("cahpp_app.horizon.imports.QFileDialog.getOpenFileName", return_value=(str(source), "")):
            window.imports.publish.click()
            wait(app, lambda: not window.jobs.tasks)
        assert not window.imports.publish.isEnabled()
        assert "est publié" in window.imports.status.text()
        assert len(database.latest_imports()) == 2
        pending = manager.pending_catalog()
        assert pending and pending["period"] == "2026-11"
        CatalogImporter(other).import_file(manager.catalog_source(pending))
        assert other.search_products("DM001")[0]["unit_price"] == 8
        errors.assert_not_called()
    window.close()
    wait(app, lambda: not window.isVisible())


if __name__ == "__main__":
    main()
