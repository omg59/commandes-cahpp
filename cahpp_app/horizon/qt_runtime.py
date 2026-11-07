"""Initialisation Qt sans importer les chemins de la base avant son choix."""

import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

_application = None


def create_application(argv=None):
    global _application
    app = QApplication.instance() or QApplication(argv or sys.argv[:1])
    _application = app
    app.setApplicationName("Commandes CAHPP Horizon")
    app.setOrganizationName("Commandes CAHPP")
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))
    if not hasattr(app, "horizon_translator"):
        translator = QTranslator(app)
        if translator.load(
            QLocale("fr_FR"),
            "qtbase",
            "_",
            QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
        ):
            app.installTranslator(translator)
        app.horizon_translator = translator
    return app
