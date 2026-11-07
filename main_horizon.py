"""Point d'entrée séparé : configurer le profil avant tout import des chemins."""

import sys


def main():
    from cahpp_app.horizon.bootstrap import configure, StartupCancelled
    from cahpp_app.horizon.startup import choose_profile

    while True:
        try:
            profile, info = configure(select_profile=choose_profile)
            break
        except StartupCancelled:
            return 0
        except (OSError, ValueError) as exc:
            from PySide6.QtWidgets import QMessageBox
            from cahpp_app.horizon.qt_runtime import create_application

            create_application()
            QMessageBox.critical(None, "Horizon — ouverture impossible", str(exc))
            if any(
                arg.split("=", 1)[0] in ("--profile", "--copy-database", "--smoke-test")
                for arg in sys.argv[1:]
            ):
                return 1
    from cahpp_app.horizon.application import run

    return run(profile, info)


if __name__ == "__main__":
    raise SystemExit(main())
