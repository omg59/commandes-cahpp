"""Premier lancement utilisateur puis réouverture du profil mémorisé."""

import sys
import sqlite3


def main():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from cahpp_app.horizon.bootstrap import configure
    from cahpp_app.horizon.qt_runtime import create_application
    from cahpp_app.horizon.startup import ProfileDialog, choose_profile

    app = create_application()
    assert "cahpp_app.paths" not in sys.modules
    failures = []

    def create():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, ProfileDialog)
            dialog.create_button.click()
            assert dialog.error.isVisible()
            dialog.name.setText("Établissement utilisateur")
            dialog.user.setText("Prénom Nom")
            dialog.create_button.click()
        except BaseException as exc:
            failures.append(exc)
            if dialog:
                dialog.reject()

    QTimer.singleShot(100, create)
    profile, info = configure([], select_profile=choose_profile)
    assert not failures, failures
    assert "cahpp_app.paths" not in sys.modules
    from cahpp_app.horizon.application import run

    assert run(profile, dict(info, smoke_test=True)) == 0
    with sqlite3.connect(profile / "data/commandes_cahpp.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert (
            db.execute("SELECT value FROM settings WHERE key='user_name'").fetchone()[0]
            == "Prénom Nom"
        )
    reopened, _ = configure(
        [],
        select_profile=lambda message: (_ for _ in ()).throw(
            AssertionError("Profil non mémorisé")
        ),
    )
    assert reopened == profile
    print("HORIZON_BETA_STARTUP_OK")


if __name__ == "__main__":
    main()
