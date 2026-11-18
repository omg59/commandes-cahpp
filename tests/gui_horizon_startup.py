"""Premier lancement utilisateur puis réouverture du profil mémorisé."""

import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch


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
    if sys.platform == "linux":
        verify_profile_switch(profile, info, create, failures)
    print("HORIZON_BETA_STARTUP_OK")


def verify_profile_switch(profile, info, create, failures):
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest
    from cahpp_app.database import Database
    from cahpp_app.horizon.application import HorizonWindow
    from cahpp_app.horizon.bootstrap import remembered_profile

    database = Database(profile / "data/commandes_cahpp.sqlite3")
    window = HorizonWindow(database, profile, info)
    window.show()
    launch = window.launch_profile
    QTimer.singleShot(100, create)
    with patch.object(window, "launch_profile", side_effect=lambda args: launch([*args, "--smoke-test"])) as start:
        window.preferences.choose_profile_button.click()
        assert not failures, failures
        start.assert_called_once()
    option, path = start.call_args.args[0]
    assert option == "--profile"
    target = Path(path)
    assert target != profile
    for _ in range(200):
        if (target / "startup-ok.json").is_file():
            break
        QTest.qWait(50)
    assert (target / "startup-ok.json").is_file()
    assert remembered_profile() == target
    assert window.isVisible()
    window.close()


if __name__ == "__main__":
    main()
