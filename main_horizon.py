"""Point d'entrée séparé : configurer le profil avant tout import des chemins."""

import sys


def main():
    from cahpp_app.horizon.bootstrap import configure

    try:
        profile, info = configure()
    except (OSError, ValueError) as exc:
        from PySide6.QtWidgets import QApplication, QMessageBox

        _app = QApplication.instance() or QApplication(sys.argv[:1])
        QMessageBox.critical(None, "Horizon — ouverture impossible", str(exc))
        return 1
    from cahpp_app.horizon.application import run

    return run(profile, info)


if __name__ == "__main__":
    raise SystemExit(main())
